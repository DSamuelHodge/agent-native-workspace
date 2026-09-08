import { sqliteTable, text, integer, real, primaryKey } from "drizzle-orm/sqlite-core";

export const users = sqliteTable("users", {
  id: text("id").primaryKey(),
  email: text("email").notNull().unique(),
  displayName: text("display_name"),
  createdAt: text("created_at").notNull(),
});

export const entities = sqliteTable("entities", {
  id: text("id").primaryKey(),
  entityType: text("entity_type").notNull(),
  teamId: text("team_id"),
  ownerId: text("owner_id").notNull(),
  name: text("name"),
  parentProjectId: text("parent_project_id"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
  deletedAt: text("deleted_at"),
});

export const documents = sqliteTable("documents", {
  entityId: text("entity_id").primaryKey(),
  contentMd: text("content_md").notNull().default(""),
  source: text("source").notNull().default("native"),
  isEditable: integer("is_editable").notNull().default(1),
});

export const channels = sqliteTable("channels", {
  entityId: text("entity_id").primaryKey(),
  channelType: text("channel_type").notNull(),
});

export const channelMessages = sqliteTable("channel_messages", {
  id: text("id").primaryKey(),
  channelId: text("channel_id").notNull(),
  parentMessageId: text("parent_message_id"),
  senderUserId: text("sender_user_id"),
  senderBotId: text("sender_bot_id"),
  content: text("content").notNull(),
  createdAt: text("created_at").notNull(),
});

export const propertyDefinitions = sqliteTable("property_definitions", {
  id: text("id").primaryKey(),
  teamId: text("team_id"),
  ownerId: text("owner_id"),
  name: text("name").notNull(),
  dataType: text("data_type").notNull(),
  isTag: integer("is_tag").notNull().default(0),
  appliesTo: text("applies_to"),
  createdAt: text("created_at"),
});

export const mentions = sqliteTable("mentions", {
  id: text("id").primaryKey(),
  sourceEntityId: text("source_entity_id"),
  sourceField: text("source_field"),
  targetEntityId: text("target_entity_id"),
  targetUserId: text("target_user_id"),
  createdAt: text("created_at"),
});

export const reminders = sqliteTable("reminders", {
  entityId: text("entity_id").primaryKey(),
  userId: text("user_id").notNull(),
  text: text("text").notNull(),
  remindAt: text("remind_at").notNull(),
  attachedEntityId: text("attached_entity_id"),
  completedAt: text("completed_at"),
});

// Extended tables for full Macro-parity tool surface (abbreviated; see 001_init.sql for full DDL)
export const channelParticipants = sqliteTable("channel_participants", {
  channelId: text("channel_id").notNull(),
  userId: text("user_id").notNull(),
  role: text("role").notNull(),
  joinedAt: text("joined_at").notNull(),
  leftAt: text("left_at"),
}, (t) => ({ pk: primaryKey({ columns: [t.channelId, t.userId] }) }));

export const botCredentials = sqliteTable("bot_credentials", { id: text("id").primaryKey(), botId: text("bot_id").notNull(), tokenHash: text("token_hash").notNull(), createdAt: text("created_at").notNull(), revokedAt: text("revoked_at") });

export const chats = sqliteTable("chats", { entityId: text("entity_id").primaryKey(), model: text("model") });
export const chatMessages = sqliteTable("chat_messages", { id: text("id").primaryKey(), chatId: text("chat_id").notNull(), role: text("role").notNull(), content: text("content"), toolCalls: text("tool_calls"), attachmentIds: text("attachment_ids"), createdAt: text("created_at").notNull() });

export const calls = sqliteTable("calls", { entityId: text("entity_id").primaryKey(), durationSeconds: integer("duration_seconds"), recordedAt: text("recorded_at").notNull(), sharedToTeam: integer("shared_to_team").notNull() });
export const callTranscriptSegments = sqliteTable("call_transcript_segments", { id: text("id").primaryKey(), callId: text("call_id").notNull(), speakerUserId: text("speaker_user_id"), startMs: integer("start_ms").notNull(), endMs: integer("end_ms").notNull(), text: text("text").notNull() });

export const inboxes = sqliteTable("inboxes", { id: text("id").primaryKey(), userId: text("user_id"), emailAddress: text("email_address").notNull(), isPrimary: integer("is_primary"), isDelegated: integer("is_delegated"), provider: text("provider") });
export const emailThreads = sqliteTable("email_threads", { entityId: text("entity_id").primaryKey(), inboxId: text("inbox_id"), subject: text("subject") });
export const emailMessages = sqliteTable("email_messages", { id: text("id").primaryKey(), threadId: text("thread_id").notNull(), sender: text("sender").notNull(), recipients: text("recipients"), cc: text("cc"), bcc: text("bcc"), body: text("body"), sentAt: text("sent_at").notNull() });
export const emailLabels = sqliteTable("email_labels", { id: text("id").primaryKey(), inboxId: text("inbox_id").notNull(), name: text("name").notNull(), isSystem: integer("is_system") });
export const emailMessageLabels = sqliteTable("email_message_labels", { messageId: text("message_id").notNull(), labelId: text("label_id").notNull() }, (t) => ({ pk: primaryKey({ columns: [t.messageId, t.labelId] }) }));

export const senderPolicies = sqliteTable("sender_policies", { id: text("id").primaryKey(), inboxId: text("inbox_id").notNull(), senderAddress: text("sender_address").notNull(), policy: text("policy").notNull() });

export const calendars = sqliteTable("calendars", { id: text("id").primaryKey(), inboxId: text("inbox_id"), userId: text("user_id"), name: text("name"), isPrimary: integer("is_primary"), isWritable: integer("is_writable") });
export const calendarEvents = sqliteTable("calendar_events", { id: text("id").primaryKey(), calendarId: text("calendar_id").notNull(), title: text("title").notNull(), startAt: text("start_at").notNull(), endAt: text("end_at").notNull(), attendees: text("attendees"), recurrenceRule: text("recurrence_rule") });

export const companies = sqliteTable("companies", { entityId: text("entity_id").primaryKey(), domains: text("domains"), lastInteractionAt: text("last_interaction_at") });
export const contacts = sqliteTable("contacts", { id: text("id").primaryKey(), companyEntityId: text("company_entity_id"), name: text("name"), email: text("email").notNull() });

export const notifications = sqliteTable("notifications", { id: text("id").primaryKey(), userId: text("user_id").notNull(), notifType: text("notif_type").notNull(), entityId: text("entity_id"), seenAt: text("seen_at"), doneAt: text("done_at"), createdAt: text("created_at").notNull() });
export const importEntities = sqliteTable("import_entities", { id: text("id").primaryKey(), userId: text("user_id").notNull(), source: text("source").notNull(), externalId: text("external_id").notNull(), status: text("status"), targetEntityId: text("target_entity_id"), createdAt: text("created_at").notNull() });
export const activityLog = sqliteTable("activity_log", { id: text("id").primaryKey(), userId: text("user_id").notNull(), actor: text("actor"), actionType: text("action_type").notNull(), entityId: text("entity_id"), propertyName: text("property_name"), fromValue: text("from_value"), toValue: text("to_value"), createdAt: text("created_at").notNull() });
export const skillFlags = sqliteTable("skill_flags", { entityId: text("entity_id").primaryKey() });
export const integrations = sqliteTable("integrations", { id: text("id").primaryKey(), userId: text("user_id"), teamId: text("team_id"), provider: text("provider").notNull(), connectedAt: text("connected_at").notNull(), toolManifest: text("tool_manifest") });
