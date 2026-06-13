/** @type {import('eslint').Linter.Config} */
export default {
  root: true,
  env: { browser: true, es2020: true },
  ignorePatterns: ["dist"],
  parserOptions: { ecmaVersion: 2020, sourceType: "module" },
  rules: {},
};
