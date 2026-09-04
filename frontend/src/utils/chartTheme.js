export const CHART_PALETTE = ["#5b4bf5", "#17b3a3", "#f0ad4e", "#d7473f", "#3567d6", "#9384ff"];

export function baseChartOptions(theme) {
  const isDark = theme === "dark";
  return {
    chart: {
      fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
      foreColor: isDark ? "#a3a6c2" : "#6b7086",
      toolbar: { show: false },
      background: "transparent",
    },
    theme: { mode: isDark ? "dark" : "light" },
    grid: { borderColor: isDark ? "#2b2d42" : "#e3e5ee" },
    colors: CHART_PALETTE,
  };
}
