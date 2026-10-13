package dev.countermeasure.llm.liquidity;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static dev.countermeasure.llm.liquidity.LiquidityDomain.*;

public final class NestedIfLiquidityPathPlanner implements LiquidityPathPlanner {

    @Override
    public Plan buildPath(Request request, List<Provider> providers) {
        List<Provider> eligible = new ArrayList<>();

        for (Provider provider : providers) {
            if (provider.enabled()) {
                if (provider.supportedPairs().contains(request.pair())) {
                    if (provider.admittedRegions().contains(request.clientRegion())) {
                        if (provider.creditApproved()) {
                            if (!provider.quoteTimestamp().isAfter(request.now())) {
                                if (!provider.quoteTimestamp().isBefore(
                                        request.now().minus(request.maxQuoteAge()))) {
                                    if (provider.availableAmount().signum() > 0) {
                                        if (venueAllowed(request, provider)) {
                                            eligible.add(provider);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        if (request.side() == Side.BUY) {
            eligible.sort(Comparator.comparing(Provider::price));
        } else {
            eligible.sort(Comparator.comparing(Provider::price).reversed());
        }

        BigDecimal remaining = request.amount();
        List<Leg> legs = new ArrayList<>();

        for (Provider provider : eligible) {
            if (remaining.signum() > 0) {
                BigDecimal amount;
                if (provider.availableAmount().compareTo(remaining) < 0) {
                    amount = provider.availableAmount();
                } else {
                    amount = remaining;
                }

                if (amount.signum() > 0) {
                    legs.add(new Leg(provider.id(), provider.venueType(), amount, provider.price()));
                    remaining = remaining.subtract(amount);
                }
            }
        }

        BigDecimal filled = request.amount().subtract(remaining);
        PlanStatus status;
        if (remaining.signum() == 0) {
            status = PlanStatus.COMPLETE;
        } else {
            status = PlanStatus.INSUFFICIENT_LIQUIDITY;
        }

        return new Plan(status, request.amount(), filled, legs);
    }

    private boolean venueAllowed(Request request, Provider provider) {
        if (request.regulatoryProfile() == RegulatoryProfile.FLEXIBLE) {
            return true;
        } else {
            if (request.regulatoryProfile() == RegulatoryProfile.US_SEF_REQUIRED) {
                if (provider.venueType() == VenueType.SEF) {
                    return true;
                } else {
                    return false;
                }
            } else {
                if (request.regulatoryProfile() == RegulatoryProfile.EU_MTF_REQUIRED) {
                    if (provider.venueType() == VenueType.MTF) {
                        return true;
                    } else {
                        return false;
                    }
                } else {
                    return false;
                }
            }
        }
    }
}
