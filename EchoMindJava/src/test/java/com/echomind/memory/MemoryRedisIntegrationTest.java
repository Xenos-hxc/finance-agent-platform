package com.echomind.memory;

import com.echomind.config.EchoMindProperties;
import com.echomind.llm.LlmGateway;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@EnabledIfEnvironmentVariable(named = "ECHOMIND_TEST_REDIS", matches = "true")
class MemoryRedisIntegrationTest {
    @TempDir Path temp;
    LettuceConnectionFactory factory;
    StringRedisTemplate redis;
    MemoryManager memory;
    LlmGateway llm;
    String user = "regression-" + UUID.randomUUID();

    @BeforeEach
    void setup() {
        factory = new LettuceConnectionFactory("127.0.0.1", 6379);
        factory.setDatabase(14);
        factory.afterPropertiesSet();
        redis = new StringRedisTemplate(factory);
        var props = new EchoMindProperties();
        props.getStorage().setMemoryPath(temp.resolve("memory.json").toString());
        llm = mock(LlmGateway.class);
        when(llm.chat(anyString(), anyString(), anyDouble(), anyInt())).thenReturn("用户咨询保修，请保留设备编号 LQ739188。");
        memory = new MemoryManager(redis, new ObjectMapper().findAndRegisterModules(), props, llm);
    }

    @AfterEach
    void cleanup() {
        redis.delete(List.of("wm:" + user + ":c", "summary:" + user + ":c"));
        factory.destroy();
    }

    void seed(int count) {
        IntStream.range(0, count).forEach(i -> memory.addMessage(user, "c", MessageRole.USER, "message-" + i));
    }

    @Test
    void compressionPreservesOrderAndWritesSummaryAndHistory() {
        seed(15);
        assertEquals(IntStream.range(10, 15).mapToObj(i -> "message-" + i).toList(),
                memory.getWorkingMemory(user, "c").stream().map(ConversationMessage::content).toList());
        assertFalse(memory.getContext(user, "c", "保修").summary().isBlank());
        assertFalse(memory.getContext(user, "new-conversation", "保修").relevantHistory().isEmpty());
        assertTrue(memory.getContext(user + "-other", "c", "保修").relevantHistory().isEmpty());
    }

    @Test
    void summaryFailureKeepsAllMessages() {
        when(llm.chat(anyString(), anyString(), anyDouble(), anyInt())).thenThrow(new RuntimeException("model unavailable"));
        seed(15);
        assertEquals(15, memory.getWorkingMemory(user, "c").size());
        assertNull(redis.opsForValue().get("summary:" + user + ":c"));
    }

    @Test
    void messageAppendedDuringSummarySurvives() {
        when(llm.chat(anyString(), anyString(), anyDouble(), anyInt())).thenAnswer(invocation -> {
            redis.opsForList().leftPush("wm:" + user + ":c", new ObjectMapper().findAndRegisterModules()
                    .writeValueAsString(new ConversationMessage(MessageRole.USER, "concurrent", java.time.Instant.now(), java.util.Map.of())));
            return "有效摘要";
        });
        seed(15);
        var messages = memory.getWorkingMemory(user, "c");
        assertEquals(6, messages.size());
        assertEquals("message-10", messages.getFirst().content());
        assertEquals("concurrent", messages.getLast().content());
    }
}
