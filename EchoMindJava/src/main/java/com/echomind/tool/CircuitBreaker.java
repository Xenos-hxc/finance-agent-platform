package com.echomind.tool;

import java.time.Duration;
import java.time.Instant;

public class CircuitBreaker {

    private final int threshold;
    private final Duration recovery;
    private CircuitState state = CircuitState.CLOSED;
    private int failCount;
    private Instant openedAt;

    public CircuitBreaker(int threshold, Duration recovery) {
        this.threshold = threshold;
        this.recovery = recovery;
    }

    public synchronized boolean allow() {
        if (state == CircuitState.CLOSED) {
            return true;
        }
        if (state == CircuitState.OPEN && openedAt != null && Instant.now().isAfter(openedAt.plus(recovery))) {
            state = CircuitState.HALF_OPEN;
            return true;
        }
        return false; // OPEN -> HALF_OPEN 的调用已占用唯一探测许可。
    }

    public synchronized void recordSuccess() {
        failCount = 0;
        state = CircuitState.CLOSED;
        openedAt = null;
    }

    public synchronized void recordFailure() {
        failCount++;
        if (failCount >= threshold) {
            state = CircuitState.OPEN;
            openedAt = Instant.now();
        }
    }

    public synchronized CircuitState state() {
        return state;
    }
}
