# Third-party source notices

`components/ai-elements/` contains selected source components installed from the official [Vercel AI Elements registry](https://elements.ai-sdk.dev/docs) on 8 September 2026. Copyright 2023 Vercel, Inc.; Apache License 2.0. The upstream notice is retained in `licenses/ai-elements-LICENSE`; full license terms are in `licenses/Apache-2.0.txt`.

`components/ui/` contains source components installed using the official [shadcn/ui](https://github.com/shadcn-ui/ui) CLI. Copyright (c) 2023 shadcn; MIT License, retained in `licenses/shadcn-ui-LICENSE`. Local adaptations correct the generated `cn` import to this application's `@/lib/utils` helper. Tailwind semantic colors are defined by the application.

The application composes AI Elements with the existing Python API rather than the AI SDK chat transport. Canvas props explicitly disable editing/deletion. Public operational summaries use Reasoning's accessible disclosure surface. Terminal output is recorded activity, not an interactive shell. Assistant content has a restricted markdown renderer and application network policy.

`ansi-to-react` remains the upstream terminal renderer. Its transitive `linkify-it` dependency is overridden to patched 5.0.2 or newer, addressing [GHSA-v245-v573-v5vm](https://github.com/advisories/GHSA-v245-v573-v5vm); the lockfile records the installed version.

Other dependencies, including React Flow, Streamdown, TanStack Query, and Geist font packages, retain their license notices in their published packages. `package-lock.json` pins the resolved package graph. No code from assistant-ui, CopilotKit, or LangGraph is copied into this frontend.
