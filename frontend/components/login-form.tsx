"use client";

import { Box, Button, Flex, Input, Stack, Text } from "@chakra-ui/react";
import { ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { ThemeToggle } from "./theme-toggle";

export function LoginForm() {
  const router = useRouter(); const [username, setUsername] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState<string | null>(null); const [pending, setPending] = useState(false);
  const submit = async (event: FormEvent) => { event.preventDefault(); setPending(true); setError(null); try { const user = await api.login(username, password); router.replace(user.must_change_password ? "/auth/change-password" : "/cases"); } catch (reason) { setError(reason instanceof ApiError && reason.status === 0 ? "DARKNETRA is unavailable. Check the API connection." : "Sign-in was not accepted."); } finally { setPending(false); } };
  return <Flex minH="100vh" align="center" justify="center" px="4" bg="linear-gradient(145deg, #061626, #0b2d3c)"><Box position="absolute" top="4" right="4"><ThemeToggle /></Box><Box w="full" maxW="420px" p={{ base: "6", md: "8" }} borderWidth="1px" borderColor="whiteAlpha.300" bg="rgba(6,22,38,.9)" borderRadius="xl" boxShadow="2xl"><Stack gap="5"><Stack gap="2"><ShieldCheck size={30} color="#2dd4bf" /><Text fontSize="2xl" fontWeight="bold">DARKNETRA</Text><Text color="fg.muted">Authorised investigator workspace</Text></Stack><form onSubmit={submit}><Stack gap="4"><Input aria-label="Username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" autoComplete="username" required /><Input aria-label="Password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" autoComplete="current-password" required />{error && <Text color="red.300" fontSize="sm">{error}</Text>}<Button type="submit" colorPalette="teal" loading={pending}>Sign in</Button></Stack></form><Text fontSize="xs" color="fg.muted">Access and activity are recorded by the service. Evidence remains available only through authorised case access.</Text></Stack></Box></Flex>;
}
