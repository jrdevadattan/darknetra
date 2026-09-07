"use client";

import { Badge, Box, Button, Flex, HStack, SimpleGrid, Spinner, Stack, Text } from "@chakra-ui/react";
import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/lib/api";

type Surface = "overview" | "evidence" | "entities" | "graph" | "findings" | "monitoring" | "alerts" | "reports" | "members" | "plugins";
const surfaces: Array<{ id: Surface; label: string; path?: string }> = [
  { id: "overview", label: "Overview" }, { id: "evidence", label: "Evidence", path: "evidence" }, { id: "entities", label: "Entities", path: "entities" },
  { id: "graph", label: "Graph", path: "graph" }, { id: "findings", label: "Findings", path: "findings" }, { id: "monitoring", label: "Monitoring", path: "watchlists" },
  { id: "alerts", label: "Alerts", path: "alerts" }, { id: "reports", label: "Reports", path: "reports" }, { id: "members", label: "Members", path: "members" }, { id: "plugins", label: "Plugins & tools", path: "plugins" },
];

function errorText(error: unknown) {
  if (error instanceof ApiError && error.status === 0) return "The API is offline. Reconnect to load case records.";
  if (error instanceof ApiError && error.status === 404) return "This case is unavailable to your account.";
  if (error instanceof ApiError && error.status === 403) return "Your case role cannot view this panel.";
  return error instanceof Error ? error.message : "The panel could not be loaded.";
}
function valueLabel(value: unknown) { if (value === null || value === undefined || value === "") return "—"; if (typeof value === "object") return JSON.stringify(value); return String(value); }

function Records({ rows, empty }: { rows: Array<Record<string, unknown>>; empty: string }) {
  if (!rows.length) return <Text color="fg.muted" fontSize="sm">{empty}</Text>;
  return <Stack gap="2">{rows.slice(0, 30).map((row, index) => { const entries = Object.entries(row).filter(([key]) => !["id", "case_id", "created_by", "updated_at"].includes(key)).slice(0, 5); return <Box key={String(row.id ?? index)} borderWidth="1px" borderColor="border" borderRadius="md" p="3" bg="bg.subtle"><HStack justify="space-between"><Text fontWeight="semibold" fontSize="sm">{valueLabel(row.title ?? row.name ?? row.display ?? row.code ?? `Record ${index + 1}`)}</Text>{Boolean(row.status) && <Badge>{valueLabel(row.status)}</Badge>}</HStack><Flex mt="2" gap="3" flexWrap="wrap">{entries.map(([key, value]) => <Text key={key} fontSize="xs" color="fg.muted"><b>{key.replaceAll("_", " ")}</b>: {valueLabel(value)}</Text>)}</Flex></Box>; })}</Stack>;
}

export function CasePanels({ caseId }: { caseId: string | null }) {
  const [surface, setSurface] = useState<Surface>("overview"); const [data, setData] = useState<unknown>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null);
  const title = useMemo(() => surfaces.find((item) => item.id === surface)?.label ?? "Overview", [surface]);
  useEffect(() => { if (!caseId) return; setLoading(true); setError(null); setData(null); const selected = surfaces.find((item) => item.id === surface); const call = surface === "overview" ? api.summary(caseId) : api.panel(caseId, selected?.path ?? surface); void call.then(setData).catch((reason) => setError(errorText(reason))).finally(() => setLoading(false)); }, [caseId, surface]);
  const body = !caseId ? <Text color="fg.muted" fontSize="sm">Choose a case to inspect its records.</Text> : loading ? <HStack color="fg.muted"><Spinner size="sm" /><Text>Loading {title.toLowerCase()}…</Text></HStack> : error ? <Box borderWidth="1px" borderColor="orange.400" borderRadius="md" p="3"><Text fontWeight="semibold">Panel unavailable</Text><Text fontSize="sm" color="fg.muted">{error}</Text></Box> : surface === "overview" ? <Summary data={data as Record<string, unknown> | null} /> : surface === "graph" ? <Graph data={data as Record<string, unknown> | null} /> : <Records rows={((data as { items?: Array<Record<string, unknown>> } | null)?.items ?? [])} empty={`No ${title.toLowerCase()} records are available for this case.`} />;
  return <Box borderTopWidth="1px" borderColor="border" bg="bg.panel" px={{ base: "3", md: "5" }} py="3"><Flex gap="2" overflowX="auto" pb="2">{surfaces.map((item) => <Button key={item.id} size="xs" flexShrink="0" variant={surface === item.id ? "subtle" : "ghost"} colorPalette={surface === item.id ? "teal" : "gray"} onClick={() => setSurface(item.id)}>{item.label}</Button>)}</Flex><Stack gap="3" maxH="230px" overflowY="auto"><HStack><Text fontWeight="bold">{title}</Text><Badge variant="outline">API-backed</Badge></HStack>{body}</Stack></Box>;
}

function Summary({ data }: { data: Record<string, unknown> | null }) { if (!data) return <Text color="fg.muted" fontSize="sm">No summary has been recorded yet.</Text>; const entries = Object.entries(data).filter(([, value]) => typeof value !== "object"); return <SimpleGrid columns={{ base: 2, md: 4 }} gap="2">{entries.map(([key, value]) => <Box key={key} p="2" borderWidth="1px" borderColor="border" borderRadius="md"><Text textTransform="capitalize" fontSize="xs" color="fg.muted">{key.replaceAll("_", " ")}</Text><Text fontWeight="bold">{valueLabel(value)}</Text></Box>)}</SimpleGrid>; }
function Graph({ data }: { data: Record<string, unknown> | null }) { const nodes = Array.isArray(data?.nodes) ? data.nodes : []; const edges = Array.isArray(data?.edges) ? data.edges : []; return <Stack gap="1"><Text fontSize="sm">{nodes.length} nodes · {edges.length} edges</Text><Text fontSize="xs" color="fg.muted">Relationship graph records are read-only. Inspect authorized provenance from the graph endpoint.</Text></Stack>; }
