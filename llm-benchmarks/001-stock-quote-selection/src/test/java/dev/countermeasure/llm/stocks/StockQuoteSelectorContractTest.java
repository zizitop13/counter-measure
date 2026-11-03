package dev.countermeasure.llm.stocks;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.function.Supplier;
import java.util.stream.Stream;

import static dev.countermeasure.llm.stocks.StockQuoteDomain.*;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StockQuoteSelectorContractTest {
    private static final Instant NOW = Instant.parse("2026-11-03T08:00:00Z");

    static Stream<Supplier<StockQuoteSelector>> selectors() {
        return Stream.of(NestedIfStockQuoteSelector::new, GuardClauseStockQuoteSelector::new);
    }

    @ParameterizedTest
    @MethodSource("selectors")
    void chooses_highest_bid_and_lowest_ask_from_accepted_quotes(Supplier<StockQuoteSelector> factory) {
        QuoteRequest request = request(DisplayMode.REALTIME, Set.of(FeedType.PRIMARY, FeedType.ALTERNATIVE));
        ConsolidatedQuote result = factory.get().select(request, List.of(
                quote("A", FeedType.PRIMARY, "100.10", "100.40", 100, 100),
                quote("B", FeedType.ALTERNATIVE, "100.20", "100.35", 100, 100),
                quote("C", FeedType.PRIMARY, "100.15", "100.30", 100, 100)));

        assertEquals(new BigDecimal("100.20"), result.bestBid());
        assertEquals("B", result.bestBidSource());
        assertEquals(new BigDecimal("100.30"), result.bestAsk());
        assertEquals("C", result.bestAskSource());
    }

    @ParameterizedTest
    @MethodSource("selectors")
    void records_first_rejection_reason(Supplier<StockQuoteSelector> factory) {
        QuoteRequest request = request(DisplayMode.REALTIME, Set.of(FeedType.PRIMARY));
        List<StockQuote> quotes = List.of(
                quote("disabled", FeedType.PRIMARY, "100", "101", 10, 10, false, true, true,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("symbol", FeedType.PRIMARY, "100", "101", 10, 10, true, true, true,
                        Set.of(ClientRegion.US), Set.of("MSFT"), NOW),
                quote("region", FeedType.PRIMARY, "100", "101", 10, 10, true, true, true,
                        Set.of(ClientRegion.EU), Set.of("AAPL"), NOW),
                quote("entitlement", FeedType.PRIMARY, "100", "101", 10, 10, true, false, true,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("future", FeedType.PRIMARY, "100", "101", 10, 10, true, true, true,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW.plusMillis(1)),
                quote("stale", FeedType.PRIMARY, "100", "101", 10, 10, true, true, true,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW.minusSeconds(3)),
                quote("crossed", FeedType.PRIMARY, "101", "100", 10, 10),
                quote("size", FeedType.PRIMARY, "100", "101", 0, 10),
                quote("feed", FeedType.ALTERNATIVE, "100", "101", 10, 10),
                quote("delayed", FeedType.PRIMARY, "100", "101", 10, 10, true, true, false,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("ok", FeedType.PRIMARY, "100", "101", 10, 10));

        ConsolidatedQuote result = factory.get().select(request, quotes);

        assertEquals(List.of(
                new QuoteEvaluation("disabled", QuoteDecision.SOURCE_DISABLED),
                new QuoteEvaluation("symbol", QuoteDecision.SYMBOL_UNSUPPORTED),
                new QuoteEvaluation("region", QuoteDecision.REGION_NOT_ALLOWED),
                new QuoteEvaluation("entitlement", QuoteDecision.ENTITLEMENT_MISSING),
                new QuoteEvaluation("future", QuoteDecision.FUTURE_TIMESTAMP),
                new QuoteEvaluation("stale", QuoteDecision.STALE_QUOTE),
                new QuoteEvaluation("crossed", QuoteDecision.INVALID_PRICE),
                new QuoteEvaluation("size", QuoteDecision.INVALID_SIZE),
                new QuoteEvaluation("feed", QuoteDecision.FEED_TYPE_NOT_ALLOWED),
                new QuoteEvaluation("delayed", QuoteDecision.REALTIME_REQUIRED),
                new QuoteEvaluation("ok", QuoteDecision.ACCEPTED)),
                result.evaluations());
    }

    @ParameterizedTest
    @MethodSource("selectors")
    void delayed_mode_allows_non_realtime_quotes(Supplier<StockQuoteSelector> factory) {
        QuoteRequest request = request(DisplayMode.DELAYED_ALLOWED, Set.of(FeedType.PRIMARY));
        ConsolidatedQuote result = factory.get().select(request, List.of(
                quote("delayed", FeedType.PRIMARY, "100", "101", 10, 10, true, true, false,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW)));
        assertEquals(QuoteDecision.ACCEPTED, result.evaluations().get(0).decision());
    }

    @Test
    void implementations_are_equivalent() {
        QuoteRequest request = request(DisplayMode.REALTIME, Set.of(FeedType.PRIMARY, FeedType.ALTERNATIVE));
        List<StockQuote> quotes = List.of(
                quote("A", FeedType.PRIMARY, "100.10", "100.40", 10, 10),
                quote("B", FeedType.ALTERNATIVE, "100.20", "100.30", 10, 10),
                quote("stale", FeedType.PRIMARY, "101", "102", 10, 10, true, true, true,
                        Set.of(ClientRegion.US), Set.of("AAPL"), NOW.minusSeconds(5)));

        assertEquals(
                new NestedIfStockQuoteSelector().select(request, quotes),
                new GuardClauseStockQuoteSelector().select(request, quotes));
    }

    private static QuoteRequest request(DisplayMode mode, Set<FeedType> types) {
        return new QuoteRequest("AAPL", ClientRegion.US, mode, types, NOW, Duration.ofSeconds(2));
    }

    private static StockQuote quote(
            String id, FeedType type, String bid, String ask, long bidSize, long askSize) {
        return quote(id, type, bid, ask, bidSize, askSize, true, true, true,
                Set.of(ClientRegion.US), Set.of("AAPL"), NOW.minusMillis(500));
    }

    private static StockQuote quote(
            String id, FeedType type, String bid, String ask, long bidSize, long askSize,
            boolean enabled, boolean entitled, boolean realtime,
            Set<ClientRegion> regions, Set<String> symbols, Instant timestamp) {
        return new StockQuote(id, type, regions, symbols, enabled, entitled, realtime,
                new BigDecimal(bid), new BigDecimal(ask), bidSize, askSize, timestamp);
    }
}
