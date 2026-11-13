import next from "eslint-config-next";
import nextTypescript from "eslint-config-next/typescript";

const config = [...next, ...nextTypescript, { ignores: [".next/", "out/", "next-env.d.ts"] }];
export default config;
