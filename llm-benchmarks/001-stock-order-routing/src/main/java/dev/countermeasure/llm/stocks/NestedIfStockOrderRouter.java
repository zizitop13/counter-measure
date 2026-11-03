package dev.countermeasure.llm.stocks;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static dev.countermeasure.llm.stocks.StockRoutingDomain.*;

public final class NestedIfStockOrderRouter implements StockOrderRouter {

    @Override
    public RoutingPlan route(OrderRequest request, List<VenueQuote> quotes) {
        List<VenueQuote> eligible = new ArrayList<>();
        List<VenueEvaluation> evaluations = new ArrayList<>();

        for (VenueQuote quote : quotes) {
            VenueDecision decision;
            if (quote.enabled()) {
                if (quote.supportedSymbols().contains(request.symbol())) {
                    if (quote.admittedRegions().contains(request.clientRegion())) {
                        if (quote.tradingPermissionGranted()) {
                            if (!quote.quoteTimestamp().isAfter(request.now())) {
                                if (!quote.quoteTimestamp().isBefore(request.now().minus(request.maxQuoteAge()))) {
                                    if (quote.availableQuantity() > 0) {
                                        if (request.orderType() == OrderType.MARKET) {
                                            if (quote.marketOrdersSupported()) {
                                                if (routingPolicyAllows(request, quote)) {
                                                    decision = VenueDecision.ELIGIBLE;
                                                    eligible.add(quote);
                                                } else {
                                                    decision = VenueDecision.ROUTING_POLICY_REJECTED;
                                                }
                                            } else {
                                                decision = VenueDecision.ORDER_TYPE_UNSUPPORTED;
                                            }
                                        } else {
                                            if (limitPriceAllows(request, quote)) {
                                                if (routingPolicyAllows(request, quote)) {
                                                    decision = VenueDecision.ELIGIBLE;
                                                    eligible.add(quote);
                                                } else {
                                                    decision = VenueDecision.ROUTING_POLICY_REJECTED;
                                                }
                                            } else {
                                                decision = VenueDecision.PRICE_OUTSIDE_LIMIT;
                                            }
                                        }
                                    } else {
                                        decision = VenueDecision.NO_LIQUIDITY;
                                    }
                                } else {
                                    decision = VenueDecision.STALE_QUOTE;
                                }
                            } else {
                                decision = VenueDecision.FUTURE_QUOTE;
                            }
                        } else {
                            decision = VenueDecision.TRADING_PERMISSION_DENIED;
                        }
                    } else {
                        decision = VenueDecision.REGION_NOT_ADMITTED;
                    }
                } else {
                    decision = VenueDecision.SYMBOL_UNSUPPORTED;
                }
            } else {
                decision = VenueDecision.DISABLED;
            }
            evaluations.add(new VenueEvaluation(quote.venueId(), decision));
        }

        if (request.side() == Side.BUY) {
            eligible.sort(Comparator.comparing(VenueQuote::price));
        } else {
            eligible.sort(Comparator.comparing(VenueQuote::price).reversed());
        }

        long remaining = request.quantity();
        List<RouteLeg> legs = new ArrayList<>();
        for (VenueQuote quote : eligible) {
            if (remaining > 0) {
                long amount;
                if (quote.availableQuantity() < remaining) {
                    amount = quote.availableQuantity();
                } else {
                    amount = remaining;
                }
                if (amount > 0) {
                    legs.add(new RouteLeg(quote.venueId(), quote.venueType(), amount, quote.price()));
                    remaining -= amount;
                }
            }
        }

        long routed = request.quantity() - remaining;
        RouteStatus status;
        if (remaining == 0) {
            status = RouteStatus.COMPLETE;
        } else {
            if (request.partialFillAllowed()) {
                if (routed > 0) {
                    status = RouteStatus.PARTIAL;
                } else {
                    status = RouteStatus.REJECTED;
                }
            } else {
                status = RouteStatus.REJECTED;
                legs.clear();
                routed = 0;
            }
        }

        return new RoutingPlan(status, request.quantity(), routed, legs, evaluations);
    }

    private boolean limitPriceAllows(OrderRequest request, VenueQuote quote) {
        if (request.side() == Side.BUY) {
            return quote.price().compareTo(request.limitPrice()) <= 0;
        } else {
            return quote.price().compareTo(request.limitPrice()) >= 0;
        }
    }

    private boolean routingPolicyAllows(OrderRequest request, VenueQuote quote) {
        if (request.routingProfile() == RoutingProfile.ANY_VENUE) {
            return true;
        } else {
            if (request.routingProfile() == RoutingProfile.LIT_ONLY) {
                if (quote.venueType() == VenueType.PRIMARY_EXCHANGE
                        || quote.venueType() == VenueType.REGIONAL_EXCHANGE) {
                    return true;
                } else {
                    return false;
                }
            } else {
                if (request.routingProfile() == RoutingProfile.NO_DARK_FOR_LARGE_ORDERS) {
                    if (request.quantity() > 10_000) {
                        if (quote.venueType() == VenueType.DARK_POOL) {
                            return false;
                        } else {
                            return true;
                        }
                    } else {
                        return true;
                    }
                } else {
                    return false;
                }
            }
        }
    }
}
