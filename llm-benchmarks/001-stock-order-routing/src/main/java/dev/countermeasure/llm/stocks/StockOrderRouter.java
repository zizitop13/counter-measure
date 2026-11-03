package dev.countermeasure.llm.stocks;

import java.util.List;
import static dev.countermeasure.llm.stocks.StockRoutingDomain.*;

public interface StockOrderRouter {
    RoutingPlan route(OrderRequest request, List<VenueQuote> quotes);
}
