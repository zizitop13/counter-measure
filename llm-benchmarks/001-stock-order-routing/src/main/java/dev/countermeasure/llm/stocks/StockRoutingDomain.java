package dev.countermeasure.llm.stocks;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public final class StockRoutingDomain {
    private StockRoutingDomain() {}

    public enum Side { BUY, SELL }
    public enum OrderType { MARKET, LIMIT }
    public enum ClientRegion { US, EU, UK }
    public enum VenueType { PRIMARY_EXCHANGE, REGIONAL_EXCHANGE, ATS, DARK_POOL }
    public enum RoutingProfile { ANY_VENUE, LIT_ONLY, NO_DARK_FOR_LARGE_ORDERS }
    public enum RouteStatus { COMPLETE, PARTIAL, REJECTED }
    public enum VenueDecision {
        ELIGIBLE,
        DISABLED,
        SYMBOL_UNSUPPORTED,
        REGION_NOT_ADMITTED,
        TRADING_PERMISSION_DENIED,
        FUTURE_QUOTE,
        STALE_QUOTE,
        NO_LIQUIDITY,
        ORDER_TYPE_UNSUPPORTED,
        PRICE_OUTSIDE_LIMIT,
        ROUTING_POLICY_REJECTED
    }

    public record OrderRequest(
            String symbol,
            Side side,
            OrderType orderType,
            long quantity,
            BigDecimal limitPrice,
            ClientRegion clientRegion,
            RoutingProfile routingProfile,
            Instant now,
            Duration maxQuoteAge,
            boolean partialFillAllowed) {

        public OrderRequest {
            if (symbol == null || symbol.isBlank()) throw new IllegalArgumentException("symbol must be set");
            if (side == null || orderType == null || clientRegion == null || routingProfile == null
                    || now == null || maxQuoteAge == null) {
                throw new IllegalArgumentException("request fields must be non-null");
            }
            if (quantity <= 0) throw new IllegalArgumentException("quantity must be positive");
            if (orderType == OrderType.LIMIT && limitPrice == null) {
                throw new IllegalArgumentException("limitPrice is required for LIMIT orders");
            }
            if (maxQuoteAge.isNegative()) throw new IllegalArgumentException("maxQuoteAge must not be negative");
        }
    }

    public record VenueQuote(
            String venueId,
            VenueType venueType,
            Set<ClientRegion> admittedRegions,
            Set<String> supportedSymbols,
            boolean enabled,
            boolean tradingPermissionGranted,
            boolean marketOrdersSupported,
            long availableQuantity,
            BigDecimal price,
            Instant quoteTimestamp) {

        public VenueQuote {
            admittedRegions = Set.copyOf(admittedRegions);
            supportedSymbols = Set.copyOf(supportedSymbols);
            if (venueId == null || venueId.isBlank() || venueType == null || price == null || quoteTimestamp == null) {
                throw new IllegalArgumentException("venue fields must be set");
            }
            if (availableQuantity < 0) throw new IllegalArgumentException("availableQuantity must not be negative");
            if (price.signum() <= 0) throw new IllegalArgumentException("price must be positive");
        }
    }

    public record VenueEvaluation(String venueId, VenueDecision decision) {}
    public record RouteLeg(String venueId, VenueType venueType, long quantity, BigDecimal price) {}

    public record RoutingPlan(
            RouteStatus status,
            long requestedQuantity,
            long routedQuantity,
            List<RouteLeg> legs,
            List<VenueEvaluation> evaluations) {

        public RoutingPlan {
            legs = List.copyOf(legs);
            evaluations = List.copyOf(evaluations);
        }
    }
}
