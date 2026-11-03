package dev.countermeasure.llm.stocks;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import static dev.countermeasure.llm.stocks.StockQuoteDomain.*;

public final class NestedIfStockQuoteSelector implements StockQuoteSelector {
    @Override
    public ConsolidatedQuote select(QuoteRequest request, List<StockQuote> quotes) {
        List<StockQuote> accepted = new ArrayList<>();
        List<QuoteEvaluation> evaluations = new ArrayList<>();

        for (StockQuote quote : quotes) {
            QuoteDecision decision;

            if (quote.enabled()) {
                if (quote.supportedSymbols().contains(request.symbol())) {
                    if (quote.allowedRegions().contains(request.clientRegion())) {
                        if (quote.entitled()) {
                            if (!quote.timestamp().isAfter(request.now())) {
                                if (!quote.timestamp().isBefore(request.now().minus(request.maxQuoteAge()))) {
                                    if (quote.bid() != null && quote.ask() != null
                                            && quote.bid().signum() > 0 && quote.ask().signum() > 0
                                            && quote.bid().compareTo(quote.ask()) <= 0) {
                                        if (quote.bidSize() > 0 && quote.askSize() > 0) {
                                            if (request.allowedFeedTypes().contains(quote.feedType())) {
                                                if (request.displayMode() == DisplayMode.REALTIME) {
                                                    if (quote.realtime()) {
                                                        decision = QuoteDecision.ACCEPTED;
                                                        accepted.add(quote);
                                                    } else {
                                                        decision = QuoteDecision.REALTIME_REQUIRED;
                                                    }
                                                } else {
                                                    decision = QuoteDecision.ACCEPTED;
                                                    accepted.add(quote);
                                                }
                                            } else {
                                                decision = QuoteDecision.FEED_TYPE_NOT_ALLOWED;
                                            }
                                        } else {
                                            decision = QuoteDecision.INVALID_SIZE;
                                        }
                                    } else {
                                        decision = QuoteDecision.INVALID_PRICE;
                                    }
                                } else {
                                    decision = QuoteDecision.STALE_QUOTE;
                                }
                            } else {
                                decision = QuoteDecision.FUTURE_TIMESTAMP;
                            }
                        } else {
                            decision = QuoteDecision.ENTITLEMENT_MISSING;
                        }
                    } else {
                        decision = QuoteDecision.REGION_NOT_ALLOWED;
                    }
                } else {
                    decision = QuoteDecision.SYMBOL_UNSUPPORTED;
                }
            } else {
                decision = QuoteDecision.SOURCE_DISABLED;
            }

            evaluations.add(new QuoteEvaluation(quote.sourceId(), decision));
        }

        BigDecimal bestBid = null;
        String bestBidSource = null;
        BigDecimal bestAsk = null;
        String bestAskSource = null;

        for (StockQuote quote : accepted) {
            if (bestBid == null) {
                bestBid = quote.bid();
                bestBidSource = quote.sourceId();
            } else {
                if (quote.bid().compareTo(bestBid) > 0) {
                    bestBid = quote.bid();
                    bestBidSource = quote.sourceId();
                }
            }

            if (bestAsk == null) {
                bestAsk = quote.ask();
                bestAskSource = quote.sourceId();
            } else {
                if (quote.ask().compareTo(bestAsk) < 0) {
                    bestAsk = quote.ask();
                    bestAskSource = quote.sourceId();
                }
            }
        }

        return new ConsolidatedQuote(
                request.symbol(),
                bestBid,
                bestBidSource,
                bestAsk,
                bestAskSource,
                evaluations);
    }
}