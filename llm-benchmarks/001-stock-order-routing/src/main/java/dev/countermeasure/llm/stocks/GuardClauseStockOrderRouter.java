package dev.countermeasure.llm.stocks;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static dev.countermeasure.llm.stocks.StockRoutingDomain.*;

public final class GuardClauseStockOrderRouter implements StockOrderRouter {

    @Override
    public RoutingPlan route(OrderRequest request, List<VenueQuote> quotes) {
        List<VenueQuote> eligible = new ArrayList<>();
        List<VenueEvaluation> evaluations = new ArrayList<>();

        for (VenueQuote quote : quotes) {
            VenueDecision decision = evaluate(request, quote);
            evaluations.add(new VenueEvaluation(quote.venueId(), decision));
            if (decision == VenueDecision.ELIGIBLE) {
                eligible.add(quote);
            }
        }

        Comparator<VenueQuote> priceOrder = Comparator.comparing(VenueQuote::price);
        if (request.side() == Side.SELL) {
            priceOrder = priceOrder.reversed();
        }
        eligible.sort(priceOrder);

        long remaining = request.quantity();
        List<RouteLeg> legs = new ArrayList<>();

        for (VenueQuote quote : eligible) {
            if (remaining <= 0) break;
            long amount = Math.min(quote.availableQuantity(), remaining);
            if (amount <= 0) continue;
            legs.add(new RouteLeg(quote.venueId(), quote.venueType(), amount, quote.price()));
            remaining -= amount;
        }

        long routed = request.quantity() - remaining;
        if (remaining == 0) {
            return new RoutingPlan(RouteStatus.COMPLETE, request.quantity(), routed, legs, evaluations);
        }
        if (!request.partialFillAllowed()) {
            return new RoutingPlan(RouteStatus.REJECTED, request.quantity(), 0, List.of(), evaluations);
        }
        if (routed == 0) {
            return new RoutingPlan(RouteStatus.REJECTED, request.quantity(), 0, List.of(), evaluations);
        }
        return new RoutingPlan(RouteStatus.PARTIAL, request.quantity(), routed, legs, evaluations);
    }

    private VenueDecision evaluate(OrderRequest request, VenueQuote quote) {
        if (!quote.enabled()) return VenueDecision.DISABLED;
        if (!quote.supportedSymbols().contains(request.symbol())) return VenueDecision.SYMBOL_UNSUPPORTED;
        if (!quote.admittedRegions().contains(request.clientRegion())) return VenueDecision.REGION_NOT_ADMITTED;
        if (!quote.tradingPermissionGranted()) return VenueDecision.TRADING_PERMISSION_DENIED;
        if (quote.quoteTimestamp().isAfter(request.now())) return VenueDecision.FUTURE_QUOTE;
        if (quote.quoteTimestamp().isBefore(request.now().minus(request.maxQuoteAge()))) return VenueDecision.STALE_QUOTE;
        if (quote.availableQuantity() <= 0) return VenueDecision.NO_LIQUIDITY;
        if (request.orderType() == OrderType.MARKET && !quote.marketOrdersSupported()) {
            return VenueDecision.ORDER_TYPE_UNSUPPORTED;
        }
        if (request.orderType() == OrderType.LIMIT && !limitPriceAllows(request, quote)) {
            return VenueDecision.PRICE_OUTSIDE_LIMIT;
        }
        if (!routingPolicyAllows(request, quote)) return VenueDecision.ROUTING_POLICY_REJECTED;
        return VenueDecision.ELIGIBLE;
    }

    private boolean limitPriceAllows(OrderRequest request, VenueQuote quote) {
        return request.side() == Side.BUY
                ? quote.price().compareTo(request.limitPrice()) <= 0
                : quote.price().compareTo(request.limitPrice()) >= 0;
    }

    private boolean routingPolicyAllows(OrderRequest request, VenueQuote quote) {
        return switch (request.routingProfile()) {
            case ANY_VENUE -> true;
            case LIT_ONLY -> quote.venueType() == VenueType.PRIMARY_EXCHANGE
                    || quote.venueType() == VenueType.REGIONAL_EXCHANGE;
            case NO_DARK_FOR_LARGE_ORDERS -> request.quantity() <= 10_000
                    || quote.venueType() != VenueType.DARK_POOL;
        };
    }
}
