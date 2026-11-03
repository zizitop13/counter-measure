package dev.countermeasure.llm.stocks;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public final class StockQuoteDomain {
    private StockQuoteDomain() {}

    public enum ClientRegion { US, EU, UK }
    public enum FeedType { PRIMARY, CONSOLIDATED, ALTERNATIVE, INDICATIVE }
    public enum DisplayMode { REALTIME, DELAYED_ALLOWED }
    public enum QuoteDecision {
        ACCEPTED,
        SOURCE_DISABLED,
        SYMBOL_UNSUPPORTED,
        REGION_NOT_ALLOWED,
        ENTITLEMENT_MISSING,
        FUTURE_TIMESTAMP,
        STALE_QUOTE,
        INVALID_PRICE,
        INVALID_SIZE,
        FEED_TYPE_NOT_ALLOWED,
        REALTIME_REQUIRED
    }

    public record QuoteRequest(
            String symbol,
            ClientRegion clientRegion,
            DisplayMode displayMode,
            Set<FeedType> allowedFeedTypes,
            Instant now,
            Duration maxQuoteAge) {
        public QuoteRequest {
            allowedFeedTypes = Set.copyOf(allowedFeedTypes);
        }
    }

    public record StockQuote(
            String sourceId,
            FeedType feedType,
            Set<ClientRegion> allowedRegions,
            Set<String> supportedSymbols,
            boolean enabled,
            boolean entitled,
            boolean realtime,
            BigDecimal bid,
            BigDecimal ask,
            long bidSize,
            long askSize,
            Instant timestamp) {
        public StockQuote {
            allowedRegions = Set.copyOf(allowedRegions);
            supportedSymbols = Set.copyOf(supportedSymbols);
        }
    }

    public record QuoteEvaluation(String sourceId, QuoteDecision decision) {}

    public record ConsolidatedQuote(
            String symbol,
            BigDecimal bestBid,
            String bestBidSource,
            BigDecimal bestAsk,
            String bestAskSource,
            List<QuoteEvaluation> evaluations) {
        public ConsolidatedQuote {
            evaluations = List.copyOf(evaluations);
        }
    }
}