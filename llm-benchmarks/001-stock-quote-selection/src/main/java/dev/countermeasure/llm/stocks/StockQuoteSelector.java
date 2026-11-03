package dev.countermeasure.llm.stocks;

import java.util.List;
import static dev.countermeasure.llm.stocks.StockQuoteDomain.*;

public interface StockQuoteSelector {
    ConsolidatedQuote select(QuoteRequest request, List<StockQuote> quotes);
}