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

import static dev.countermeasure.llm.stocks.StockRoutingDomain.*;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StockOrderRouterContractTest {
    private static final Instant NOW = Instant.parse("2026-11-03T08:00:00Z");
    private static final Duration MAX_AGE = Duration.ofSeconds(2);

    static Stream<Supplier<StockOrderRouter>> routers() {
        return Stream.of(NestedIfStockOrderRouter::new, GuardClauseStockOrderRouter::new);
    }

    @ParameterizedTest
    @MethodSource("routers")
    void routes_buy_to_lowest_prices_and_splits_quantity(Supplier<StockOrderRouter> factory) {
        OrderRequest request = request(Side.BUY, OrderType.MARKET, 700, null, RoutingProfile.ANY_VENUE, true);
        RoutingPlan plan = factory.get().route(request, List.of(
                quote("A", VenueType.PRIMARY_EXCHANGE, "101.20", 300),
                quote("B", VenueType.REGIONAL_EXCHANGE, "100.90", 400),
                quote("C", VenueType.ATS, "101.00", 400)));

        assertEquals(RouteStatus.COMPLETE, plan.status());
        assertEquals(700, plan.routedQuantity());
        assertEquals(List.of(
                new RouteLeg("B", VenueType.REGIONAL_EXCHANGE, 400, bd("100.90")),
                new RouteLeg("C", VenueType.ATS, 300, bd("101.00"))), plan.legs());
    }

    @ParameterizedTest
    @MethodSource("routers")
    void routes_sell_to_highest_prices(Supplier<StockOrderRouter> factory) {
        OrderRequest request = request(Side.SELL, OrderType.MARKET, 500, null, RoutingProfile.ANY_VENUE, true);
        RoutingPlan plan = factory.get().route(request, List.of(
                quote("A", VenueType.PRIMARY_EXCHANGE, "100.90", 500),
                quote("B", VenueType.REGIONAL_EXCHANGE, "101.30", 200),
                quote("C", VenueType.ATS, "101.10", 500)));

        assertEquals(List.of(
                new RouteLeg("B", VenueType.REGIONAL_EXCHANGE, 200, bd("101.30")),
                new RouteLeg("C", VenueType.ATS, 300, bd("101.10"))), plan.legs());
    }

    @ParameterizedTest
    @MethodSource("routers")
    void reports_each_rejection_reason(Supplier<StockOrderRouter> factory) {
        OrderRequest request = request(Side.BUY, OrderType.MARKET, 100, null, RoutingProfile.ANY_VENUE, true);
        List<VenueQuote> quotes = List.of(
                quote("disabled", VenueType.ATS, "100", 100, false, true, true, Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("symbol", VenueType.ATS, "100", 100, true, true, true, Set.of(ClientRegion.US), Set.of("MSFT"), NOW),
                quote("region", VenueType.ATS, "100", 100, true, true, true, Set.of(ClientRegion.EU), Set.of("AAPL"), NOW),
                quote("permission", VenueType.ATS, "100", 100, true, false, true, Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("future", VenueType.ATS, "100", 100, true, true, true, Set.of(ClientRegion.US), Set.of("AAPL"), NOW.plusMillis(1)),
                quote("stale", VenueType.ATS, "100", 100, true, true, true, Set.of(ClientRegion.US), Set.of("AAPL"), NOW.minusSeconds(3)),
                quote("empty", VenueType.ATS, "100", 0, true, true, true, Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("market", VenueType.ATS, "100", 100, true, true, false, Set.of(ClientRegion.US), Set.of("AAPL"), NOW),
                quote("ok", VenueType.ATS, "100", 100));

        RoutingPlan plan = factory.get().route(request, quotes);

        assertEquals(List.of(
                new VenueEvaluation("disabled", VenueDecision.DISABLED),
                new VenueEvaluation("symbol", VenueDecision.SYMBOL_UNSUPPORTED),
                new VenueEvaluation("region", VenueDecision.REGION_NOT_ADMITTED),
                new VenueEvaluation("permission", VenueDecision.TRADING_PERMISSION_DENIED),
                new VenueEvaluation("future", VenueDecision.FUTURE_QUOTE),
                new VenueEvaluation("stale", VenueDecision.STALE_QUOTE),
                new VenueEvaluation("empty", VenueDecision.NO_LIQUIDITY),
                new VenueEvaluation("market", VenueDecision.ORDER_TYPE_UNSUPPORTED),
                new VenueEvaluation("ok", VenueDecision.ELIGIBLE)), plan.evaluations());
    }

    @ParameterizedTest
    @MethodSource("routers")
    void limit_buy_rejects_prices_above_limit_and_limit_sell_rejects_below_limit(Supplier<StockOrderRouter> factory) {
        RoutingPlan buy = factory.get().route(
                request(Side.BUY, OrderType.LIMIT, 100, "100.00", RoutingProfile.ANY_VENUE, true),
                List.of(quote("too-high", VenueType.ATS, "100.01", 100), quote("ok", VenueType.ATS, "100.00", 100)));
        RoutingPlan sell = factory.get().route(
                request(Side.SELL, OrderType.LIMIT, 100, "100.00", RoutingProfile.ANY_VENUE, true),
                List.of(quote("too-low", VenueType.ATS, "99.99", 100), quote("ok", VenueType.ATS, "100.00", 100)));

        assertEquals(VenueDecision.PRICE_OUTSIDE_LIMIT, buy.evaluations().get(0).decision());
        assertEquals(VenueDecision.ELIGIBLE, buy.evaluations().get(1).decision());
        assertEquals(VenueDecision.PRICE_OUTSIDE_LIMIT, sell.evaluations().get(0).decision());
        assertEquals(VenueDecision.ELIGIBLE, sell.evaluations().get(1).decision());
    }

    @ParameterizedTest
    @MethodSource("routers")
    void synthetic_routing_profiles_filter_venues(Supplier<StockOrderRouter> factory) {
        RoutingPlan litOnly = factory.get().route(
                request(Side.BUY, OrderType.MARKET, 100, null, RoutingProfile.LIT_ONLY, true),
                List.of(quote("dark", VenueType.DARK_POOL, "99", 100), quote("lit", VenueType.PRIMARY_EXCHANGE, "101", 100)));
        RoutingPlan large = factory.get().route(
                request(Side.BUY, OrderType.MARKET, 10_001, null, RoutingProfile.NO_DARK_FOR_LARGE_ORDERS, true),
                List.of(quote("dark", VenueType.DARK_POOL, "99", 20_000), quote("ats", VenueType.ATS, "101", 20_000)));
        RoutingPlan boundary = factory.get().route(
                request(Side.BUY, OrderType.MARKET, 10_000, null, RoutingProfile.NO_DARK_FOR_LARGE_ORDERS, true),
                List.of(quote("dark", VenueType.DARK_POOL, "99", 10_000)));

        assertEquals(VenueDecision.ROUTING_POLICY_REJECTED, litOnly.evaluations().get(0).decision());
        assertEquals(VenueDecision.ROUTING_POLICY_REJECTED, large.evaluations().get(0).decision());
        assertEquals(VenueDecision.ELIGIBLE, boundary.evaluations().get(0).decision());
    }

    @ParameterizedTest
    @MethodSource("routers")
    void partial_fill_policy_controls_final_status_and_legs(Supplier<StockOrderRouter> factory) {
        List<VenueQuote> quotes = List.of(quote("A", VenueType.ATS, "100", 300));

        RoutingPlan allowed = factory.get().route(
                request(Side.BUY, OrderType.MARKET, 500, null, RoutingProfile.ANY_VENUE, true), quotes);
        RoutingPlan forbidden = factory.get().route(
                request(Side.BUY, OrderType.MARKET, 500, null, RoutingProfile.ANY_VENUE, false), quotes);

        assertEquals(RouteStatus.PARTIAL, allowed.status());
        assertEquals(300, allowed.routedQuantity());
        assertEquals(1, allowed.legs().size());

        assertEquals(RouteStatus.REJECTED, forbidden.status());
        assertEquals(0, forbidden.routedQuantity());
        assertEquals(List.of(), forbidden.legs());
    }

    @Test
    void implementations_are_equivalent() {
        OrderRequest request = request(Side.BUY, OrderType.LIMIT, 900, "101.00", RoutingProfile.LIT_ONLY, true);
        List<VenueQuote> quotes = List.of(
                quote("primary", VenueType.PRIMARY_EXCHANGE, "100.80", 400),
                quote("regional", VenueType.REGIONAL_EXCHANGE, "100.90", 300),
                quote("ats", VenueType.ATS, "100.50", 500),
                quote("expensive", VenueType.PRIMARY_EXCHANGE, "101.10", 500));

        assertEquals(
                new NestedIfStockOrderRouter().route(request, quotes),
                new GuardClauseStockOrderRouter().route(request, quotes));
    }

    private static OrderRequest request(
            Side side, OrderType type, long quantity, String limit, RoutingProfile profile, boolean partial) {
        return new OrderRequest("AAPL", side, type, quantity, limit == null ? null : bd(limit),
                ClientRegion.US, profile, NOW, MAX_AGE, partial);
    }

    private static VenueQuote quote(String id, VenueType type, String price, long quantity) {
        return quote(id, type, price, quantity, true, true, true,
                Set.of(ClientRegion.US, ClientRegion.EU, ClientRegion.UK), Set.of("AAPL"), NOW.minusMillis(500));
    }

    private static VenueQuote quote(
            String id, VenueType type, String price, long quantity,
            boolean enabled, boolean permission, boolean marketSupported,
            Set<ClientRegion> regions, Set<String> symbols, Instant timestamp) {
        return new VenueQuote(id, type, regions, symbols, enabled, permission, marketSupported,
                quantity, bd(price), timestamp);
    }

    private static BigDecimal bd(String value) {
        return new BigDecimal(value);
    }
}
