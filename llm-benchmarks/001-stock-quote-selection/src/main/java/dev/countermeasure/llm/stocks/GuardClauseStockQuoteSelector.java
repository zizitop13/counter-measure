package dev.countermeasure.llm.stocks;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static dev.countermeasure.llm.stocks.StockQuoteDomain.*;

public final class GuardClauseStockQuoteSelector implements StockQuoteSelector {
    @Override
    public ConsolidatedQuote select(QuoteRequest request, List<StockQuote> quotes) {
        List<StockQuote> accepted = new ArrayList<>();
        List<QuoteEvaluation> evaluations = new ArrayList<>();

        for (StockQuote quote : quotes) {
            QuoteDecision decision = evaluate(request, quote);
            evaluations.add(new QuoteEvaluation(quote.sourceId(), decision));

            if (decision == QuoteDecision.ACCEPTED) {
                accepted.add(quote);
            }
        }

        StockQuote bidQuote = accepted.stream()
                .max(Comparator.comparing(StockQuote::bid))
                .orElse(null);

        StockQuote askQuote = accepted.stream()
                .min(Comparator.comparing(StockQuote::ask))
                .orElse(null);

        return new ConsolidatedQuote(
                request.symbol(),
                bidQuote == null ? null : bidQuote.bid(),
                bidQuote == null ? null : bidQuote.sourceId(),
                askQuote == null ? null : askQuote.ask(),
                askQuote == null ? null : askQuote.sourceId(),
                evaluations);
    }

    private QuoteDecision evaluate(QuoteRequest request, StockQuote quote) {
        if (!quote.enabled()) {
            return QuoteDecision.SOURCE_DISABLED;
        }
        if (!quote.supportedSymbols().contains(request.symbol())) {
            return QuoteDecision.SYMBOL_UNSUPPORTED;
        }
        if (!quote.allowedRegions().contains(request.clientRegion())) {
            return QuoteDecision.REGION_NOT_ALLOWED;
        }
        if (!quote.entitled()) {
            return QuoteDecision.ENTITLEMENT_MISSING;
        }
        if (quote.timestamp().isAfter(request.now())) {
            return QuoteDecision.FUTURE_TIMESTAMP;
        }
        if (quote.timestamp().isBefore(request.now().minus(request.maxQuoteAge()))) {
            return QuoteDecision.STALE_QUOTE;
        }
        if (!hasValidPrice(quote)) {
            return QuoteDecision.INVALID_PRICE;
        }
        if (quote.bidSize() <= 0 || quote.askSize() <= 0) {
            return QuoteDecision.INVALID_SIZE;
        }
        if (!request.allowedFeedTypes().contains(quote.feedType())) {
            return QuoteDecision.FEED_TYPE_NOT_ALLOWED;
        }
        if (request.displayMode() == DisplayMode.REALTIME && !quote.realtime()) {
            return QuoteDecision.REALTIME_REQUIRED;
        }
        return QuoteDecision.ACCEPTED;
    }

    private boolean hasValidPrice(StockQuote quote) {
        return quote.bid() != null
                && quote.ask() != null
                && quote.bid().signum() > 0
                && quote.ask().signum() > 0
                && quote.bid().compareTo(quote.ask()) <= 0;
    }
}