package com.echomind.evaluation;

public record QualityScores(
        double relevance,
        double accuracy,
        double completeness,
        double helpfulness,
        boolean judgeFailed,
        String error
) {
    public double overall() {
        // 四项 0–1 裁判分等权平均，例如 (0.9+0.8+0.7+0.85)/4=0.8125。
        // 对话轮次用 overall>=0.75 判通过；它是回答质量阈值，不是实际业务完成率。
        return (relevance + accuracy + completeness + helpfulness) / 4.0;
    }
}
