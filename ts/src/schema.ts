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
