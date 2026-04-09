import { ExecArgs } from "@medusajs/framework/types";
import { ContainerRegistrationKeys } from "@medusajs/framework/utils";
import seedDemoData from "./seed";

type QueryGraphResponse<T> = {
  data?: T[];
};

type ProductRecord = {
  id: string;
  handle: string;
};

export default async function bootstrapStorefrontData({
  container,
}: ExecArgs) {
  const logger = container.resolve(ContainerRegistrationKeys.LOGGER);
  const query = container.resolve(ContainerRegistrationKeys.QUERY);

  const { data } = (await query.graph({
    entity: "product",
    fields: ["id", "handle"],
    filters: {
      handle: "t-shirt",
    },
  })) as QueryGraphResponse<ProductRecord>;

  if (data?.length) {
    logger.info("Demo storefront data already exists, skipping seed.");
    return;
  }

  logger.info("Demo storefront data not found, running seed.");
  await seedDemoData({ container } as ExecArgs);
}