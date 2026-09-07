"use client";

import { Badge, Box, Button, Flex, HStack, IconButton, Input, Separator, Spinner, Stack, Text, Textarea } from "@chakra-ui/react";
import { AlertCircle, Archive, Bot, ChevronRight, CircleDot, FileSearch, FolderOpen, LogOut, Menu, MessageSquare, Plus, RefreshCw, Send, ShieldCheck, WifiOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { Case, Chat, ExecutionSnapshot, Thread, ThreadMessage, User } from "@/lib/types";
import { ThemeToggle } from "./theme-toggle";
import { CasePanels } from "./case-panels";

type Notice = { tone: "error" | "warning" | "info"; title: string; body: string } | null;

function messageText(message: ThreadMessage) {
  return message.blocks.map((block) => block.text ?? block.content ?? "").filter(Boolean).join("\n");
}

function noticeFor(error: unknown): Notice {
  if (!(error instanceof ApiError)) return { tone: "error", title: "Unexpected error", body: "The workspace could not complete this request." };
  if (error.status === 0 || error.status === 503) return { tone: "warning", title: "Backend unavailable", body: "Saved case records are not available until DARKNETRA reconnects." };
  if (error.status === 401) return { tone: "warning", title: "Session expired", body: "Sign in again to continue." };
  if (error.status === 403) return { tone: "error", title: "Access denied", body: "Your role does not allow this operation." };
  if (error.status === 404) return { tone: "warning", title: "Case unavailable", body: "This case may not exist or is unavailable to your account." };
  return { tone: "error", title: error.code ?? "Request failed", body: error.message };
}

function NoticeCard({ notice }: { notice: Notice }) {
  if (!notice) return null;
  const palette = notice.tone === "error" ? "red" : notice.tone === "warning" ? "orange" : "teal";
  return <Box borderWidth="1px" borderColor={`${palette}.500`} bg={`${palette}.950`} borderRadius="md" p="3" mx="4" mb="3">
    <HStack align="start"><AlertCircle size={18} /><Stack gap="0"><Text fontWeight="bold">{notice.title}</Text><Text fontSize="sm" color="fg.muted">{notice.body}</Text></Stack></HStack>
  </Box>;
}

function ActivityPanel({ snapshot, onCancel }: { snapshot: ExecutionSnapshot | null; onCancel: () => void }) {
  return <Box borderLeftWidth="1px" borderColor="border" bg="bg.panel" minW="280px" maxW="350px" overflowY="auto">
    <Flex h="58px" px="4" align="center" justify="space-between" borderBottomWidth="1px" borderColor="border"><HStack><CircleDot size={17} color="#2dd4bf" /><Text fontWeight="bold">Activity</Text></HStack>{snapshot?.run_status === "RUNNING" && <Button size="xs" colorPalette="red" variant="outline" onClick={onCancel}>Cancel run</Button>}</Flex>
    {!snapshot && <Stack p="5" gap="2" color="fg.muted"><Bot size={22} /><Text fontWeight="medium" color="fg">No active run</Text><Text fontSize="sm">Tool activity appears here only after the backend records it.</Text></Stack>}
    {snapshot && <Stack p="4" gap="3">
      <HStack justify="space-between"><Badge colorPalette={snapshot.run_status === "RUNNING" ? "teal" : "gray"}>{snapshot.run_status}</Badge><Text fontSize="xs" color="fg.muted">cursor {snapshot.cursor}</Text></HStack>
      {snapshot.truncated && <Box p="2" bg="orange.950" borderRadius="sm" fontSize="xs">History is incomplete; the API marked this run truncated.</Box>}
      {snapshot.nodes.length === 0 && <Text fontSize="sm" color="fg.muted">The run has no recorded activity yet.</Text>}
      {snapshot.nodes.map((node) => <Box key={node.id} p="3" bg="bg.subtle" borderLeftWidth="3px" borderColor={node.status === "completed" ? "teal.400" : node.status === "denied" || node.status === "failed" ? "red.400" : "orange.400"} borderRadius="sm">
        <HStack justify="space-between" align="start"><Text fontWeight="semibold" fontSize="sm">{node.label}</Text><Badge size="sm" variant="subtle">{node.status}</Badge></HStack>
        {node.summary && <Text mt="1" fontSize="xs" color="fg.muted">{node.summary}</Text>}
        <HStack mt="2" gap="2" flexWrap="wrap"><Text fontSize="xs" color="fg.muted">{node.phase ?? "working"}</Text>{node.duration_ms != null && <Text fontSize="xs" color="fg.muted">{node.duration_ms}ms</Text>}{node.evidence_codes?.map((code) => <Badge key={code} size="sm" colorPalette="teal">{code}</Badge>)}</HStack>
      </Box>)}
    </Stack>}
  </Box>;
}

function ChatPane({ thread, messages, pending, onSend }: { thread: Thread | null; messages: ThreadMessage[]; pending: boolean; onSend: (content: string) => Promise<void> }) {
  const [content, setContent] = useState("");
  const submit = async (event: FormEvent) => { event.preventDefault(); const value = content.trim(); if (!value || !thread || pending) return; setContent(""); await onSend(value); };
  if (!thread) return <Flex flex="1" direction="column" align="center" justify="center" gap="3" color="fg.muted"><MessageSquare size={28} /><Text>Select a case thread to view its recorded conversation.</Text></Flex>;
  return <Flex flex="1" minW="0" direction="column" bg="bg">
    <Flex h="58px" px="5" align="center" justify="space-between" borderBottomWidth="1px" borderColor="border"><Stack gap="0"><Text fontWeight="bold">{thread.title}</Text><Text fontSize="xs" color="fg.muted">{thread.harness} · {thread.status}</Text></Stack><Badge colorPalette={thread.active_run_id ? "teal" : "gray"}>{thread.active_run_id ? "RUNNING" : "CASE THREAD"}</Badge></Flex>
    <Stack flex="1" overflowY="auto" p={{ base: "4", md: "6" }} gap="4">
      {messages.length === 0 && <Box maxW="560px" p="5" borderWidth="1px" borderStyle="dashed" borderColor="border" borderRadius="lg"><FileSearch size={22} /><Text mt="2" fontWeight="semibold">No messages recorded</Text><Text fontSize="sm" color="fg.muted">Ask a case question to start a tracked run. Panel data continues to come from the API.</Text></Box>}
      {messages.map((message) => <Box key={message.id} alignSelf={message.role === "USER" ? "flex-end" : "flex-start"} maxW="84%" px="4" py="3" borderRadius="lg" bg={message.role === "USER" ? "teal.800" : "bg.subtle"} borderWidth={message.role === "USER" ? "0" : "1px"} borderColor="border">
        <Text fontSize="xs" color="fg.muted" mb="1">{message.role} · {new Date(message.at).toLocaleString()}</Text><Text whiteSpace="pre-wrap">{messageText(message) || "[No renderable message content]"}</Text>
        {message.claims.map((claim, index) => <HStack key={index} mt="2" gap="1" flexWrap="wrap"><Badge colorPalette={claim.kind === "confirmed" ? "green" : "teal"}>{claim.kind ?? "claim"}</Badge>{claim.evidence_codes?.map((code) => <Badge key={code} variant="outline" colorPalette="teal">{code}</Badge>)}</HStack>)}
      </Box>)}
      {pending && <HStack color="teal.300"><Spinner size="sm" /><Text fontSize="sm">Run requested; reconciling recorded activity…</Text></HStack>}
    </Stack>
    <Box p="4" borderTopWidth="1px" borderColor="border"><form onSubmit={submit}><HStack align="end"><Textarea aria-label="Case message" value={content} onChange={(event) => setContent(event.target.value)} placeholder="Ask about recorded case evidence…" minH="74px" disabled={pending} /><IconButton aria-label="Send case message" type="submit" colorPalette="teal" disabled={!content.trim() || pending}><Send size={18} /></IconButton></HStack><Text mt="2" fontSize="xs" color="fg.muted">Messages initiate backend runs. The client does not turn chat prose into case records.</Text></form></Box>
  </Flex>;
}

export function WorkspaceShell({ initialCaseId }: { initialCaseId?: string }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null); const [cases, setCases] = useState<Case[]>([]); const [chats, setChats] = useState<Chat[]>([]);
  const [caseId, setCaseId] = useState<string | null>(initialCaseId ?? null); const [threads, setThreads] = useState<Thread[]>([]); const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]); const [snapshot, setSnapshot] = useState<ExecutionSnapshot | null>(null); const [notice, setNotice] = useState<Notice>(null); const [loading, setLoading] = useState(true); const [pending, setPending] = useState(false);
  const selectedCase = useMemo(() => cases.find((item) => item.id === caseId) ?? null, [cases, caseId]); const selectedThread = useMemo(() => threads.find((item) => item.id === threadId) ?? null, [threads, threadId]);

  const loadWorkspace = useCallback(async () => {
    setLoading(true); setNotice(null);
    try { const [me, casePage, chatPage] = await Promise.all([api.me(), api.cases(), api.chats()]); setUser(me); setCases(casePage.items); setChats(chatPage.items); setCaseId((current) => current ?? casePage.items[0]?.id ?? null); }
    catch (error) { const nextNotice = noticeFor(error); setNotice(nextNotice); if (error instanceof ApiError && error.status === 401) router.replace("/auth/login"); }
    finally { setLoading(false); }
  }, [router]);

  useEffect(() => { void loadWorkspace(); }, [loadWorkspace]);
  useEffect(() => { if (initialCaseId) setCaseId(initialCaseId); }, [initialCaseId]);
  useEffect(() => { if (!caseId) { setThreads([]); setThreadId(null); return; } void api.threads(caseId).then((page) => { setThreads(page.items); setThreadId((current) => current && page.items.some((thread) => thread.id === current) ? current : page.items[0]?.id ?? null); }).catch((error) => setNotice(noticeFor(error))); }, [caseId]);
  useEffect(() => { if (!caseId || !threadId) { setMessages([]); setSnapshot(null); return; } void api.messages(caseId, threadId).then((page) => setMessages(page.items)).catch((error) => setNotice(noticeFor(error))); }, [caseId, threadId]);
  useEffect(() => {
    if (!caseId || !threadId || !snapshot || (snapshot.run_status !== "RUNNING" && snapshot.run_status !== "QUEUED")) return;
    const controller = new AbortController();
    void api.subscribeRunEvents(caseId, threadId, snapshot.run_id, snapshot.cursor, (frame) => {
      const payload = frame.data as Record<string, unknown>;
      if (frame.event === "activity.updated" && payload.id) {
        setSnapshot((current) => current ? { ...current, cursor: Number(frame.id ?? current.cursor), nodes: current.nodes.some((node) => node.id === payload.id) ? current.nodes.map((node) => node.id === payload.id ? { ...node, ...payload } : node) : [...current.nodes, payload as never] } : current);
      }
      if (frame.event === "run.finished" || frame.event === "run.cancelled" || frame.event === "run.error") {
        void api.execution(caseId, threadId, snapshot.run_id).then(setSnapshot).catch((error) => setNotice(noticeFor(error)));
        void api.messages(caseId, threadId).then((page) => setMessages(page.items)).catch(() => undefined);
      }
    }, controller.signal).catch((error) => { if (!controller.signal.aborted) setNotice(noticeFor(error)); });
    return () => controller.abort();
  }, [caseId, threadId, snapshot?.run_id, snapshot?.run_status]);

  const send = async (content: string) => {
    if (!caseId || !threadId) return; setPending(true); setNotice(null);
    try { const run = await api.postMessage(caseId, threadId, content); const [page, execution] = await Promise.all([api.messages(caseId, threadId), api.execution(caseId, threadId, run.run_id)]); setMessages(page.items); setSnapshot(execution); }
    catch (error) { setNotice(noticeFor(error)); }
    finally { setPending(false); }
  };
  const cancel = async () => { if (!caseId || !threadId || !snapshot) return; try { await api.cancelRun(caseId, threadId, snapshot.run_id); setSnapshot(await api.execution(caseId, threadId, snapshot.run_id)); } catch (error) { setNotice(noticeFor(error)); } };

  return <Flex h="100vh" minH="600px" direction="column" bg="bg">
    <Flex h="52px" px="4" align="center" justify="space-between" bg="#071a2b" borderBottomWidth="1px" borderColor="whiteAlpha.200"><HStack><ShieldCheck size={19} color="#2dd4bf" /><Text letterSpacing="0.12em" fontWeight="bold" fontSize="sm">DARKNETRA</Text>{selectedCase?.demo && <Badge colorPalette="orange">SYNTHETIC DEMO</Badge>}</HStack><HStack><Text display={{ base: "none", md: "block" }} fontSize="xs" color="gray.400">{user ? `${user.display_name} · ${user.global_role}` : "Checking session"}</Text><ThemeToggle /><IconButton aria-label="Reload workspace" size="sm" variant="ghost" onClick={() => void loadWorkspace()}><RefreshCw size={16} /></IconButton></HStack></Flex>
    <NoticeCard notice={notice} />
    {loading ? <Flex flex="1" align="center" justify="center" gap="3"><Spinner color="teal.400" /><Text>Loading workspace…</Text></Flex> : <Flex flex="1" minH="0">
      <Box w={{ base: "244px", lg: "300px" }} flexShrink="0" borderRightWidth="1px" borderColor="border" bg="bg.panel" overflowY="auto"><Stack p="3" gap="4">
        <HStack justify="space-between"><Text fontWeight="bold">Case workspace</Text><IconButton aria-label="Open navigation" size="xs" variant="ghost"><Menu size={16} /></IconButton></HStack>
        <Stack gap="1"><Text fontSize="xs" textTransform="uppercase" color="fg.muted" fontWeight="bold">Cases</Text>{cases.length === 0 && <Text fontSize="sm" color="fg.muted">No accessible cases.</Text>}{cases.map((item) => <Button key={item.id} justifyContent="space-between" variant={item.id === caseId ? "subtle" : "ghost"} colorPalette={item.id === caseId ? "teal" : "gray"} onClick={() => { setCaseId(item.id); router.replace(`/cases/${item.id}`); }}><HStack minW="0"><FolderOpen size={16} /><Text truncate>{item.code}</Text></HStack><ChevronRight size={14} /></Button>)}</Stack>
        <Separator /><Stack gap="1"><Text fontSize="xs" textTransform="uppercase" color="fg.muted" fontWeight="bold">Case threads</Text>{threads.length === 0 && <Text fontSize="sm" color="fg.muted">No threads for this case.</Text>}{threads.map((item) => <Button key={item.id} justifyContent="start" textAlign="left" variant={item.id === threadId ? "subtle" : "ghost"} colorPalette={item.id === threadId ? "teal" : "gray"} onClick={() => setThreadId(item.id)}><MessageSquare size={16} /><Text truncate>{item.title}</Text></Button>)}</Stack>
        <Separator /><Stack gap="1"><Text fontSize="xs" textTransform="uppercase" color="fg.muted" fontWeight="bold">Private chats</Text>{chats.length === 0 && <Text fontSize="sm" color="fg.muted">No private chats.</Text>}{chats.slice(0, 4).map((chat) => <HStack key={chat.id} px="2" py="1" color="fg.muted"><Bot size={15} /><Text fontSize="sm" truncate>{chat.title}</Text></HStack>)}</Stack>
        <Box flex="1" /><Button variant="outline" colorPalette="gray" justifyContent="start" onClick={() => void api.logout().finally(() => router.replace("/auth/login"))}><LogOut size={16} /> Sign out</Button>
      </Stack></Box>
      <Flex flex="1" minW="0" direction="column"><ChatPane thread={selectedThread} messages={messages} pending={pending} onSend={send} /><CasePanels caseId={caseId} /></Flex><ActivityPanel snapshot={snapshot} onCancel={cancel} />
    </Flex>}
  </Flex>;
}
