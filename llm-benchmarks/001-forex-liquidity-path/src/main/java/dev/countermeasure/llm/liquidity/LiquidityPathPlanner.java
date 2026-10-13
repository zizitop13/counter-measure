package dev.countermeasure.llm.liquidity;

import java.util.List;

import static dev.countermeasure.llm.liquidity.LiquidityDomain.Plan;
import static dev.countermeasure.llm.liquidity.LiquidityDomain.Provider;
import static dev.countermeasure.llm.liquidity.LiquidityDomain.Request;

public interface LiquidityPathPlanner {
    Plan buildPath(Request request, List<Provider> providers);
}
