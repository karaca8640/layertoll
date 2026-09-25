// Modified for LayerToll: eslint-config-next 16 ships a native flat config (ESLint 9).
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextVitals,
  ...nextTs,
  { ignores: [".next/**", "out/**", "node_modules/**"] },
];

export default eslintConfig;
