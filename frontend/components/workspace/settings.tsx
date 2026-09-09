"use client";
import { useLanguage } from "./language";
import { useState } from "react";
import { useTheme } from "next-themes";
import {
  Archive,
  Monitor,
  Moon,
  Settings,
  SlidersHorizontal,
  Sun,
} from "lucide-react";
import type { Chat, WorkspaceData } from "@/lib/chat-types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArchivedChats } from "./archived-chats";
import { NotificationSettings } from "./notifications";
import { IntegrationSettings } from "./integration-settings";
import { LanguageSettings } from "./language";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export function WorkspaceSettings({
  data,
  onRestore,
  onOpen,
}: {
  data: WorkspaceData;
  onRestore: (chat: Chat) => Promise<void>;
  onOpen: (chat: Chat) => void;
}) {
  const { t } = useLanguage();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const archiveCount = data.chats.filter((chat) => chat.archivedAt).length;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="icon-button"
          aria-label={t("Settings")}
          title={t("Settings")}
        >
          <Settings size={18} />
        </button>
      </DialogTrigger>
      <DialogContent className="settings-dialog">
        <DialogHeader>
          <DialogTitle>{t("Settings")}</DialogTitle>
          <DialogDescription>
            Make this workspace feel like yours.
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="general" className="settings-tabs">
          <TabsList aria-label={t("Settings sections")}>
            <TabsTrigger value="general">
              <SlidersHorizontal size={15} />
              {t("General")}
            </TabsTrigger>
            <TabsTrigger value="archived">
              <Archive size={15} />
              {t("Archived chats")}
              <span className="archive-count">{archiveCount}</span>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="general" className="settings-general">
            <LanguageSettings />
            <fieldset className="theme-settings">
              <legend>{t("Appearance")}</legend>
              <div className="theme-options">
                {[
                  { value: "light", label: t("Light"), Icon: Sun },
                  { value: "dark", label: t("Dark"), Icon: Moon },
                  { value: "system", label: t("System"), Icon: Monitor },
                ].map(({ value, label, Icon }) => (
                  <label
                    key={value}
                    className={`theme-option ${theme === value ? "selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name="theme"
                      value={value}
                      checked={theme === value}
                      onChange={() => setTheme(value)}
                    />
                    <Icon size={22} strokeWidth={1.6} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <p>
                Your choice is saved in this browser. System follows your
                device.
              </p>
            </fieldset>
            <NotificationSettings />
            <IntegrationSettings />
          </TabsContent>
          <TabsContent value="archived">
            <ArchivedChats
              data={data}
              onRestore={onRestore}
              onOpen={(chat) => {
                setOpen(false);
                onOpen(chat);
              }}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
