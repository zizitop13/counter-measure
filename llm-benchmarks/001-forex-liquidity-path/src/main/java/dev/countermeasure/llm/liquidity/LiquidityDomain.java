package dev.countermeasure.llm.liquidity;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public final class LiquidityDomain {
    private LiquidityDomain() {
    }

    public enum Side {
        BUY,
        SELL
    }

    public enum ClientRegion {
        US,
        EU,
        UK
    }

    public enum VenueType {
        SEF,
        MTF,
        ECN,
        OTC
    }

    /**
     * Synthetic policy used only by this benchmark.
     * It intentionally borrows familiar market-structure names but is not a statement of actual regulation.
     */
    public enum RegulatoryProfile {
        FLEXIBLE,
        US_SEF_REQUIRED,
        EU_MTF_REQUIRED
    }

    public enum PlanStatus {
        COMPLETE,
        INSUFFICIENT_LIQUIDITY
    }

    public record Request(
            String pair,
            Side side,
            BigDecimal amount,
            ClientRegion clientRegion,
            RegulatoryProfile regulatoryProfile,
            Instant now,
            Duration maxQuoteAge) {

        public Request {
            if (pair == null || pair.isBlank()) {
                throw new IllegalArgumentException("pair must be set");
            }
            if (side == null || amount == null || clientRegion == null
                    || regulatoryProfile == null || now == null || maxQuoteAge == null) {
                throw new IllegalArgumentException("request fields must be non-null");
            }
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (maxQuoteAge.isNegative()) {
                throw new IllegalArgumentException("maxQuoteAge must not be negative");
            }
        }
    }

    public record Provider(
            String id,
            VenueType venueType,
            Set<ClientRegion> admittedRegions,
            Set<String> supportedPairs,
            boolean enabled,
            boolean creditApproved,
            BigDecimal availableAmount,
            BigDecimal price,
            Instant quoteTimestamp) {

        public Provider {
            if (id == null || id.isBlank() || venueType == null || admittedRegions == null
                    || supportedPairs == null || availableAmount == null || price == null
                    || quoteTimestamp == null) {
                throw new IllegalArgumentException("provider fields must be non-null");
            }
            admittedRegions = Set.copyOf(admittedRegions);
            supportedPairs = Set.copyOf(supportedPairs);
            if (availableAmount.signum() < 0) {
                throw new IllegalArgumentException("availableAmount must not be negative");
            }
            if (price.signum() <= 0) {
                throw new IllegalArgumentException("price must be positive");
            }
        }
    }

    public record Leg(
            String providerId,
            VenueType venueType,
            BigDecimal amount,
            BigDecimal price) {
    }

    public record Plan(
            PlanStatus status,
            BigDecimal requestedAmount,
            BigDecimal filledAmount,
            List<Leg> legs) {

        public Plan {
            legs = List.copyOf(legs);
        }
    }
}
