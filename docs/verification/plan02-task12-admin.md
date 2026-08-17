# Plan 02 Task 12 verification

RED phase outcomes:

- prepare: success
- focused administration tests: failure

```text

> @darknetra/web@2.2.0 test /home/runner/work/darknetra/darknetra/apps/web
> vitest run -- src/features/admin

[33m(!) Your Vite config uses features that are unsupported by `configLoader: 'native'`, which is planned to become the default in a future major version of Vite:
  - ESM syntax in a file loaded as CommonJS (vitest.config.ts:1:1). Use a `.mjs` extension or set `"type": "module"` in the closest package.json
Set `VITE_CONFIG_NATIVE_IGNORE_WARNING=true` to suppress this warning.[39m

[1m[30m[46m RUN [49m[39m[22m [36mv4.1.10 [39m[90m/home/runner/work/darknetra/darknetra/apps/web[39m

 [32m✓[39m src/features/auth/auth-session.test.tsx [2m([22m[2m10 tests[22m[2m)[22m[33m 1135[2mms[22m[39m
     [33m[2m✓[22m[39m uses investigator credential semantics, supports keyboard submit, and clears the password [33m 487[2mms[22m[39m
 [32m✓[39m src/features/cases/live-case-views.test.tsx [2m([22m[2m6 tests[22m[2m)[22m[33m 325[2mms[22m[39m
 [31m❯[39m src/features/admin/admin-reads.test.tsx [2m([22m[2m0 test[22m[2m)[22m
 [32m✓[39m src/lib/api/__tests__/client.test.ts [2m([22m[2m9 tests[22m[2m)[22m[32m 22[2mms[22m[39m
 [32m✓[39m src/features/overview/overview-live-view.test.tsx [2m([22m[2m2 tests[22m[2m)[22m[32m 280[2mms[22m[39m
 [32m✓[39m src/features/cases/queries.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 6[2mms[22m[39m
 [32m✓[39m src/lib/api/health.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 7[2mms[22m[39m
 [32m✓[39m src/navigation/darknetra-navigation.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/components/darknetra/investigator-primitives.test.tsx [2m([22m[2m9 tests[22m[2m)[22m[32m 185[2mms[22m[39m
 [32m✓[39m src/features/cases/cases-table.test.tsx [2m([22m[2m1 test[22m[2m)[22m[33m 355[2mms[22m[39m
     [33m[2m✓[22m[39m supports visible search and links rows to a case [33m 354[2mms[22m[39m
 [32m✓[39m src/navigation/sidebar/sidebar-items.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/config/metadata-contract.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 4[2mms[22m[39m
 [32m✓[39m src/config/app-config.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m

[31m⎯⎯⎯⎯⎯⎯[39m[1m[41m Failed Suites 1 [49m[22m[31m⎯⎯⎯⎯⎯⎯⎯[39m

[41m[1m FAIL [22m[49m src/features/admin/admin-reads.test.tsx[2m [ src/features/admin/admin-reads.test.tsx ][22m
[31m[1mError[22m: Failed to resolve import "./roles/role-permission-matrix" from "src/features/admin/admin-reads.test.tsx". Does the file exist?[39m
  Plugin: [35mvite:import-analysis[39m
  File: [36m/home/runner/work/darknetra/darknetra/apps/web/src/features/admin/admin-reads.test.tsx[39m:7:37
[33m  2  |  import { render, screen } from "@testing-library/react";
  3  |  import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
  4  |  import { RolePermissionMatrix } from "./roles/role-permission-matrix";
     |                                        ^
  5  |  import { UserTable } from "./users/user-table";
  6  |  var _jsxFileName = "/home/runner/work/darknetra/darknetra/apps/web/src/features/admin/admin-reads.test.tsx";[39m
[90m [2m❯[22m TransformPluginContext._formatLog ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m31066:39[22m[39m
[90m [2m❯[22m TransformPluginContext.error ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m31063:14[22m[39m
[90m [2m❯[22m normalizeUrl ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m28008:18[22m[39m
[90m [2m❯[22m ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m28076:30[22m[39m
[90m [2m❯[22m TransformPluginContext.transform ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m28044:4[22m[39m
[90m [2m❯[22m EnvironmentPluginContainer.transform ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m30851:14[22m[39m
[90m [2m❯[22m loadAndTransform ../../node_modules/.pnpm/vite@8.2.1_@types+node@22.20.1_jiti@2.7.0/node_modules/vite/dist/node/chunks/node.js:[2m20619:26[22m[39m

[31m[2m⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯[22m[39m


[2m Test Files [22m [1m[31m1 failed[39m[22m[2m | [22m[1m[32m12 passed[39m[22m[90m (13)[39m
[2m      Tests [22m [1m[32m53 passed[39m[22m[90m (53)[39m
[2m   Start at [22m 23:32:09
[2m   Duration [22m 17.81s[2m (transform 484ms, setup 2.17s, import 2.04s, tests 2.33s, environment 9.24s)[22m

/home/runner/work/darknetra/darknetra/apps/web:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @darknetra/web@2.2.0 test: `vitest run -- src/features/admin`
Exit status 1
```
