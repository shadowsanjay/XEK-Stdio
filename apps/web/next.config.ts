import type { NextConfig } from "next";
const config: NextConfig = { ...(process.env.NEXT_STANDALONE === "1" ? { output: "standalone" as const } : {}) };
export default config;
