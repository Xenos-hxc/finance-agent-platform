package com.echomind.agent;

import com.echomind.intent.IntentCategory;
import com.echomind.intent.UrgencyLevel;
import com.echomind.llm.LlmGateway;
import com.echomind.trace.RequestTraceStore;
import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class RoutingRegressionTest {
    @Test
    void explicitCompositeProblemCallsBothSpecialists() {
        LlmGateway llm = (system, prompt, temperature, tokens) -> "处理步骤";
        var router = new AgentOrchestrator(null, Map.of(
                AgentType.TECHNICAL, List.of(new TechnicalAgent(llm, null)),
                AgentType.BILLING, List.of(new BillingAgent(llm, null))), new RequestTraceStore());
        var request = new AgentRequest("登录报错401，同时重复扣款99元", "u", "c", "", List.of(),
                Map.of("error_code", List.of("401"), "amount", List.of("99元")),
                IntentCategory.TECHNICAL_LOGIN,"technical", UrgencyLevel.MEDIUM,0.9,"test-id");
        var result = router.run(request);
        assertTrue(result.agentTypes().containsAll(List.of(AgentType.TECHNICAL, AgentType.BILLING)));
        assertEquals(AgentType.TECHNICAL, result.primaryAgent());
        assertTrue(router.getToolTrace("test-id").isPresent());
    }
}
