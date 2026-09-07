import { createClient } from "@libsql/client";
import { eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/libsql";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as schema from "../src/schema.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const dbPath =
  process.env.DATABASE_URL?.replace(/^file:/, "") ??
  path.join(root, "data/agent_native.db");

const client = createClient({ url: `file:${dbPath}` });
const db = drizzle(client, { schema });

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const email = `drizzle-${Date.now()}@example.com`;
const userId = randomUUID();
const now = new Date().toISOString();
await db.insert(schema.users).values({ id: userId, email, displayName: "Drizzle", createdAt: now });

const entityId = randomUUID();
await db.insert(schema.entities).values({
  id: entityId,
  entityType: "document",
  ownerId: userId,
  name: "Drizzle task",
  createdAt: now,
  updatedAt: now,
});
await db.insert(schema.documents).values({ entityId, contentMd: "from drizzle" });

const loaded = await db.select().from(schema.documents).where(eq(schema.documents.entityId, entityId));
assert(loaded.length === 1 && loaded[0].contentMd === "from drizzle", "document mismatch");

const channelId = randomUUID();
await db.insert(schema.entities).values({
  id: channelId,
  entityType: "channel",
  ownerId: userId,
  name: "drizzle-ops",
  createdAt: now,
  updatedAt: now,
});
await db.insert(schema.channels).values({ entityId: channelId, channelType: "team" });
const msgId = randomUUID();
await db.insert(schema.channelMessages).values({
  id: msgId,
  channelId,
  senderUserId: userId,
  content: "hi from drizzle",
  createdAt: now,
});
const msgs = await db.select().from(schema.channelMessages).where(eq(schema.channelMessages.id, msgId));
assert(msgs[0]?.content === "hi from drizzle", "channel message mismatch");

client.close();
console.log("drizzle orm tests ok");
