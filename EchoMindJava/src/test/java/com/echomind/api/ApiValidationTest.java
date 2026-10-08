package com.echomind.api;

import com.echomind.api.dto.EvalRunRequest;
import com.echomind.knowledge.KnowledgeBaseService;
import com.echomind.tool.KnowledgeToolManager;
import com.echomind.tool.ToolResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Validation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ApiValidationTest {
    MockMvc mvc;
    KnowledgeToolManager tools;
    KnowledgeBaseService knowledge;

    @BeforeEach
    void setup() {
        tools = mock(KnowledgeToolManager.class);
        knowledge = mock(KnowledgeBaseService.class);
        when(tools.searchWithRewrite(anyString(), anyInt()))
                .thenReturn(new ToolResult<>(true, List.of(), "knowledge_search", null, false, 0, false));
        mvc = MockMvcBuilders.standaloneSetup(new EchoMindController(null, null, null, tools, knowledge,
                null, null, null, null, new ObjectMapper(), null)).build();
    }

    @Test
    void frontendTopKAndLegacyNameAreAccepted() throws Exception {
        mvc.perform(post("/search").param("query", "退款").param("top_k", "1")).andExpect(status().isOk());
        verify(tools).searchWithRewrite("退款", 1);
        mvc.perform(post("/search").param("query", "账单").param("topK", "2")).andExpect(status().isOk());
        verify(tools).searchWithRewrite("账单", 2);
    }

    @ParameterizedTest
    @ValueSource(strings = {"0", "-1", "101"})
    void rejectsInvalidLimits(String count) throws Exception {
        mvc.perform(post("/search").param("query", "退款").param("top_k", count))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(tools);
    }

    @Test
    void rejectsBlankSearch() throws Exception {
        mvc.perform(post("/search").param("query", "  ")).andExpect(status().isBadRequest());
    }

    @ParameterizedTest
    @ValueSource(strings = {"{", "{}", "null", "[]", "[1]", "[{\"title\":\"x\",\"content\":\"  \"}]"})
    void rejectsInvalidJsonBeforeWriting(String payload) throws Exception {
        mvc.perform(multipart("/knowledge/upload").file(new MockMultipartFile("file", "bad.json",
                "application/json", payload.getBytes(StandardCharsets.UTF_8)))).andExpect(status().isBadRequest());
        verifyNoInteractions(knowledge);
    }

    @Test
    void unsupportedFileIsRejected() throws Exception {
        mvc.perform(multipart("/knowledge/upload").file(new MockMultipartFile("file", "a.pdf",
                "application/pdf", new byte[]{1}))).andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void emptyAndInvalidUtf8AreRejected() throws Exception {
        for (byte[] payload : List.of(new byte[0], new byte[]{(byte) 0xff})) {
            mvc.perform(multipart("/knowledge/upload").file(new MockMultipartFile("file", "a.txt",
                    "text/plain", payload))).andExpect(status().isBadRequest());
        }
    }

    @Test
    void invalidNestedEvalInputIsRejected() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var request = new EvalRunRequest(List.of(new EvalRunRequest.IntentCase("", "")),
                    List.of(new EvalRunRequest.DialogCase(null, null, null, null)));
            assertEquals(3, factory.getValidator().validate(request).size());
        }
    }
}
