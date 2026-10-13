package dev.countermeasure.llm.liquidity;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static dev.countermeasure.llm.liquidity.LiquidityDomain.*;

public final class GuardClauseLiquidityPathPlanner implements LiquidityPathPlanner {

    @Override
    public Plan buildPath(Request request, List<Provider> providers) {
        List<Provider> eligible = new ArrayList<>();

        for (Provider provider : providers) {
            if (!provider.enabled()) {
                continue;
            }
            if (!provider.supportedPairs().contains(request.pair())) {
                continue;
            }
            if (!provider.admittedRegions().contains(request.clientRegion())) {
                continue;
            }
            if (!provider.creditApproved()) {
                continue;
            }
            if (provider.quoteTimestamp().isAfter(request.now())) {
                continue;
            }
            if (provider.quoteTimestamp().isBefore(request.now().minus(request.maxQuoteAge()))) {
                continue;
            }
            if (provider.availableAmount().signum() <= 0) {
                continue;
            }
            if (!venueAllowed(request, provider)) {
                continue;
            }
            eligible.add(provider);
        }

        Comparator<Provider> priceOrder = Comparator.comparing(Provider::price);
        if (request.side() == Side.SELL) {
            priceOrder = priceOrder.reversed();
        }
        eligible.sort(priceOrder);

        BigDecimal remaining = request.amount();
        List<Leg> legs = new ArrayList<>();

        for (Provider provider : eligible) {
            if (remaining.signum() <= 0) {
                break;
            }

            BigDecimal amount = provider.availableAmount().min(remaining);
            if (amount.signum() <= 0) {
                continue;
            }

            legs.add(new Leg(provider.id(), provider.venueType(), amount, provider.price()));
            remaining = remaining.subtract(amount);
        }

        BigDecimal filled = request.amount().subtract(remaining);
        PlanStatus status = remaining.signum() == 0
                ? PlanStatus.COMPLETE
                : PlanStatus.INSUFFICIENT_LIQUIDITY;

        return new Plan(status, request.amount(), filled, legs);
    }

    private boolean venueAllowed(Request request, Provider provider) {
        return switch (request.regulatoryProfile()) {
            case FLEXIBLE -> true;
            case US_SEF_REQUIRED -> provider.venueType() == VenueType.SEF;
            case EU_MTF_REQUIRED -> provider.venueType() == VenueType.MTF;
        };
    }
}
