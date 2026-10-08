package com.echomind.tool;

import com.echomind.knowledge.KnowledgeBaseService;
import com.echomind.knowledge.SearchResult;
import com.echomind.llm.LlmGateway;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class KnowledgeToolRegressionTest {
    List<SearchResult> docs = List.of(new SearchResult("1","a","old",0.9,0,Map.of()),
            new SearchResult("2","b","next",0.8,0,Map.of()),new SearchResult("3","c","last",0.7,0,Map.of()));

    @Test
    void cacheInvalidationReturnsUpdatedKnowledge() {
        var kb=mock(KnowledgeBaseService.class);
        when(kb.search("q",1)).thenReturn(docs.subList(0,1));
        var tools=new KnowledgeToolManager(kb,(s,p,t,n)->"[]",new ObjectMapper());
        assertFalse(tools.search("q",1).cached());
        assertTrue(tools.search("q",1).cached());
        when(kb.search("q",1)).thenReturn(docs.subList(1,2));
        tools.invalidateCache();
        assertEquals("2",tools.search("q",1).data().getFirst().id());
    }

    @Test
    void actualKnowledgeFailureOpensCircuit() {
        var kb=mock(KnowledgeBaseService.class);
        when(kb.search(anyString(),anyInt())).thenThrow(new IllegalStateException("offline"));
        var tools=new KnowledgeToolManager(kb,(s,p,t,n)->"[]",new ObjectMapper());
        for(int i=0;i<5;i++) assertNotNull(tools.searchWithRewrite("q",2).error());
        assertEquals("circuit open",tools.searchWithRewrite("q",2).error());
    }

    @Test
    void halfOpenHasOnlyOneProbe() {
        var breaker=new CircuitBreaker(1,Duration.ofSeconds(-1));
        breaker.recordFailure();
        assertTrue(breaker.allow());
        assertFalse(breaker.allow());
        breaker.recordSuccess();
        assertTrue(breaker.allow());
    }

    @ParameterizedTest
    @ValueSource(strings={"[0,0]","[true,1]","[-1]","[99]","[]","garbage"})
    void invalidRerankingFallsBackWithoutClaimingApplied(String invalid) {
        var kb=mock(KnowledgeBaseService.class);
        when(kb.search(anyString(),anyInt())).thenReturn(docs);
        LlmGateway llm=(s,p,t,n)->p.contains("改写")?"[]":invalid;
        var result=new KnowledgeToolManager(kb,llm,new ObjectMapper()).searchWithRewrite("q",2);
        assertEquals(2,result.data().size());
        assertFalse(result.reranked());
    }
}
