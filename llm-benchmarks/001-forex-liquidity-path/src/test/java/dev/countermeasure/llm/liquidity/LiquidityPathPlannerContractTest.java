package dev.countermeasure.llm.liquidity;

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

import static dev.countermeasure.llm.liquidity.LiquidityDomain.*;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LiquidityPathPlannerContractTest {
    private static final Instant NOW = Instant.parse("2026-10-13T08:00:00Z");
    private static final Duration MAX_AGE = Duration.ofSeconds(2);

    static Stream<Supplier<LiquidityPathPlanner>> planners() {
        return Stream.of(NestedIfLiquidityPathPlanner::new, GuardClauseLiquidityPathPlanner::new);
    }

    @ParameterizedTest
    @MethodSource("planners")
    void buy_uses_best_prices_and_splits_across_providers(Supplier<LiquidityPathPlanner> factory) {
        Request request = request(Side.BUY, "7000000", RegulatoryProfile.FLEXIBLE);

        List<Provider> providers = List.of(
                provider("A", VenueType.ECN, "1.0815", "3000000"),
                provider("B", VenueType.MTF, "1.0812", "4000000"),
                provider("C", VenueType.OTC, "1.0814", "4000000"));

        Plan plan = factory.get().buildPath(request, providers);

        assertEquals(PlanStatus.COMPLETE, plan.status());
        assertEquals(bd("7000000"), plan.filledAmount());
        assertEquals(List.of(
                new Leg("B", VenueType.MTF, bd("4000000"), bd("1.0812")),
                new Leg("C", VenueType.OTC, bd("3000000"), bd("1.0814"))),
                plan.legs());
    }

    @ParameterizedTest
    @MethodSource("planners")
    void sell_uses_highest_prices_first(Supplier<LiquidityPathPlanner> factory) {
        Request request = request(Side.SELL, "5000000", RegulatoryProfile.FLEXIBLE);

        Plan plan = factory.get().buildPath(request, List.of(
                provider("A", VenueType.ECN, "1.0812", "5000000"),
                provider("B", VenueType.MTF, "1.0818", "2000000"),
                provider("C", VenueType.OTC, "1.0815", "5000000")));

        assertEquals(List.of(
                new Leg("B", VenueType.MTF, bd("2000000"), bd("1.0818")),
                new Leg("C", VenueType.OTC, bd("3000000"), bd("1.0815"))),
                plan.legs());
    }

    @ParameterizedTest
    @MethodSource("planners")
    void filters_ineligible_providers_before_building_path(Supplier<LiquidityPathPlanner> factory) {
        Request request = request(Side.BUY, "1000000", RegulatoryProfile.FLEXIBLE);

        List<Provider> providers = List.of(
                provider("disabled", VenueType.ECN, "1.0700", "1000000", false, true,
                        Set.of(ClientRegion.EU), Set.of("EUR/USD"), NOW),
                provider("wrong-pair", VenueType.ECN, "1.0700", "1000000", true, true,
                        Set.of(ClientRegion.EU), Set.of("GBP/USD"), NOW),
                provider("wrong-region", VenueType.ECN, "1.0700", "1000000", true, true,
                        Set.of(ClientRegion.US), Set.of("EUR/USD"), NOW),
                provider("no-credit", VenueType.ECN, "1.0700", "1000000", true, false,
                        Set.of(ClientRegion.EU), Set.of("EUR/USD"), NOW),
                provider("future", VenueType.ECN, "1.0700", "1000000", true, true,
                        Set.of(ClientRegion.EU), Set.of("EUR/USD"), NOW.plusMillis(1)),
                provider("stale", VenueType.ECN, "1.0700", "1000000", true, true,
                        Set.of(ClientRegion.EU), Set.of("EUR/USD"), NOW.minusSeconds(3)),
                provider("empty", VenueType.ECN, "1.0700", "0", true, true,
                        Set.of(ClientRegion.EU), Set.of("EUR/USD"), NOW),
                provider("eligible", VenueType.ECN, "1.0900", "1000000"));

        Plan plan = factory.get().buildPath(request, providers);

        assertEquals(PlanStatus.COMPLETE, plan.status());
        assertEquals(List.of(
                new Leg("eligible", VenueType.ECN, bd("1000000"), bd("1.0900"))),
                plan.legs());
    }

    @ParameterizedTest
    @MethodSource("planners")
    void synthetic_us_profile_accepts_only_sef(Supplier<LiquidityPathPlanner> factory) {
        Request request = request(Side.BUY, "2000000", RegulatoryProfile.US_SEF_REQUIRED);

        Plan plan = factory.get().buildPath(request, List.of(
                provider("cheap-mtf", VenueType.MTF, "1.0700", "2000000"),
                provider("sef", VenueType.SEF, "1.0900", "2000000")));

        assertEquals(List.of(
                new Leg("sef", VenueType.SEF, bd("2000000"), bd("1.0900"))),
                plan.legs());
    }

    @ParameterizedTest
    @MethodSource("planners")
    void synthetic_eu_profile_accepts_only_mtf(Supplier<LiquidityPathPlanner> factory) {
        Request request = request(Side.BUY, "2000000", RegulatoryProfile.EU_MTF_REQUIRED);

        Plan plan = factory.get().buildPath(request, List.of(
                provider("cheap-sef", VenueType.SEF, "1.0700", "2000000"),
                provider("mtf", VenueType.MTF, "1.0900", "2000000")));

        assertEquals(List.of(
                new Leg("mtf", VenueType.MTF, bd("2000000"), bd("1.0900"))),
                plan.legs());
    }

    @ParameterizedTest
    @MethodSource("planners")
    void returns_partial_plan_when_eligible_liquidity_is_insufficient(Supplier<LiquidityPathPlanner> factory) {
        Request request = request(Side.BUY, "5000000", RegulatoryProfile.FLEXIBLE);

        Plan plan = factory.get().buildPath(request, List.of(
                provider("A", VenueType.ECN, "1.0800", "1000000"),
                provider("B", VenueType.MTF, "1.0810", "1500000")));

        assertEquals(PlanStatus.INSUFFICIENT_LIQUIDITY, plan.status());
        assertEquals(bd("2500000"), plan.filledAmount());
        assertEquals(2, plan.legs().size());
    }

    @Test
    void implementations_are_equivalent_for_a_mixed_scenario() {
        Request request = request(Side.BUY, "4500000", RegulatoryProfile.FLEXIBLE);
        List<Provider> providers = List.of(
                provider("A", VenueType.ECN, "1.0804", "1000000"),
                provider("B", VenueType.MTF, "1.0801", "2500000"),
                provider("C", VenueType.OTC, "1.0802", "2000000"),
                provider("stale", VenueType.ECN, "1.0700", "9000000", true, true,
                        Set.of(ClientRegion.EU), Set.of("EUR/USD"), NOW.minusSeconds(5)));

        Plan nested = new NestedIfLiquidityPathPlanner().buildPath(request, providers);
        Plan guards = new GuardClauseLiquidityPathPlanner().buildPath(request, providers);

        assertEquals(nested, guards);
    }

    private static Request request(Side side, String amount, RegulatoryProfile regulatoryProfile) {
        return new Request(
                "EUR/USD",
                side,
                bd(amount),
                ClientRegion.EU,
                regulatoryProfile,
                NOW,
                MAX_AGE);
    }

    private static Provider provider(
            String id,
            VenueType venue,
            String price,
            String available) {
        return provider(id, venue, price, available, true, true,
                Set.of(ClientRegion.EU, ClientRegion.US, ClientRegion.UK),
                Set.of("EUR/USD"),
                NOW.minusMillis(500));
    }

    private static Provider provider(
            String id,
            VenueType venue,
            String price,
            String available,
            boolean enabled,
            boolean creditApproved,
            Set<ClientRegion> admittedRegions,
            Set<String> pairs,
            Instant timestamp) {
        return new Provider(
                id,
                venue,
                admittedRegions,
                pairs,
                enabled,
                creditApproved,
                bd(available),
                bd(price),
                timestamp);
    }

    private static BigDecimal bd(String value) {
        return new BigDecimal(value);
    }
}
