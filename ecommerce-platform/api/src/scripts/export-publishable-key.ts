import fs from "node:fs/promises";

import { ExecArgs } from "@medusajs/framework/types";
import { ContainerRegistrationKeys } from "@medusajs/framework/utils";
import {
  createApiKeysWorkflow,
  linkSalesChannelsToApiKeyWorkflow,
} from "@medusajs/medusa/core-flows";

type QueryGraphResponse<T> = {
  data?: T[];
};

type ApiKeyRecord = {
  id: string;
  title?: string;
  token?: string;
};

type SalesChannelRecord = {
  id: string;
};

const PUBLISHABLE_KEY_TITLE = "Webshop";

function getUsableToken(token?: string) {
  const value = token?.trim();

  if (!value || value.includes("*")) {
    return "";
  }

  return value;
}

async function findPublishableKey(query: any, filters: Record<string, unknown>) {
  const { data } = (await query.graph({
    entity: "api_key",
    fields: ["id", "title", "token", "type"],
    filters: {
      type: "publishable",
      ...filters,
    },
  })) as QueryGraphResponse<ApiKeyRecord>;

  return data?.[0] ?? null;
}

async function getDefaultSalesChannelId(query: any) {
  const { data } = (await query.graph({
    entity: "sales_channel",
    fields: ["id", "name"],
    filters: {
      name: "Default Sales Channel",
    },
  })) as QueryGraphResponse<SalesChannelRecord>;

  const salesChannel = data?.[0];

  if (!salesChannel) {
    throw new Error("Default Sales Channel was not found.");
  }

  return salesChannel.id;
}

async function createAndLinkPublishableKey(container: any, query: any) {
  const salesChannelId = await getDefaultSalesChannelId(query);
  const {
    result: [createdApiKey],
  } = await createApiKeysWorkflow(container).run({
    input: {
      api_keys: [
        {
          title: PUBLISHABLE_KEY_TITLE,
          type: "publishable",
          created_by: "",
        },
      ],
    },
  });

  const createdKey = createdApiKey as ApiKeyRecord;

  await linkSalesChannelsToApiKeyWorkflow(container).run({
    input: {
      id: createdKey.id,
      add: [salesChannelId],
    },
  });

  return createdKey;
}

async function ensurePublishableKey(container: any, query: any, logger: any) {
  const existingKey =
    (await findPublishableKey(query, { title: PUBLISHABLE_KEY_TITLE })) ??
    (await findPublishableKey(query, {}));

  const existingToken = getUsableToken(existingKey?.token);

  if (existingKey && existingToken) {
    return {
      id: existingKey.id,
      token: existingToken,
    };
  }

  if (existingKey) {
    logger.info(
      "Existing publishable key token is not exportable, creating a new key."
    );
  } else {
    logger.info("No publishable key found, creating one now.");
  }

  const createdKey = await createAndLinkPublishableKey(container, query);
  const createdToken = getUsableToken(createdKey.token);

  if (createdToken) {
    return {
      id: createdKey.id,
      token: createdToken,
    };
  }

  const fetchedCreatedKey = await findPublishableKey(query, { id: createdKey.id });
  const fetchedToken = getUsableToken(fetchedCreatedKey?.token);

  if (!fetchedCreatedKey || !fetchedToken) {
    throw new Error("Unable to resolve a usable publishable API key token.");
  }

  return {
    id: fetchedCreatedKey.id,
    token: fetchedToken,
  };
}

async function upsertEnvValue(filePath: string, key: string, value: string) {
  let content = "";

  try {
    content = await fs.readFile(filePath, "utf8");
  } catch (error: any) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }

  const nextLine = `${key}=${value}`;
  const matcher = new RegExp(`^${key}=.*$`, "m");

  if (matcher.test(content)) {
    content = content.replace(matcher, nextLine);
  } else if (content.trim()) {
    content = `${content.trimEnd()}\n${nextLine}\n`;
  } else {
    content = `${nextLine}\n`;
  }

  await fs.writeFile(filePath, content, "utf8");
}

export default async function exportPublishableKey({
  container,
}: ExecArgs) {
  const logger = container.resolve(ContainerRegistrationKeys.LOGGER);
  const query = container.resolve(ContainerRegistrationKeys.QUERY);
  const rootEnvFile = process.env.ROOT_ENV_FILE;

  if (!rootEnvFile) {
    throw new Error("ROOT_ENV_FILE is required to export the publishable key.");
  }

  const publishableKey = await ensurePublishableKey(container, query, logger);

  await upsertEnvValue(
    rootEnvFile,
    "NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY",
    publishableKey.token
  );

  logger.info(`Saved NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY to ${rootEnvFile}.`);
}