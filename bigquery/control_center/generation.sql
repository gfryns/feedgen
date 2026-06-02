/**
    Copyright 2024 Google LLC
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        https://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
 */


CREATE OR REPLACE FUNCTION `[DATASET]`.TitlesPrompt(
  LANGUAGE STRING,
  EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>>,
  PRODUCTS ARRAY<STRUCT<properties STRING, image_info STRING>>) AS (
  CONCAT(
    "## System Instructions\n\n",
    REPLACE(
      """-- TITLES_PROMPT""",
      '{{LANGUAGE}}', LANGUAGE
    ),
    "\n\n",
    IF(ARRAY_LENGTH(EXAMPLES) > 0,
      CONCAT(
        "## Examples\n\n",
        ARRAY_TO_STRING(
          (SELECT ARRAY_AGG(CONCAT("**User:**\n", properties, "\n\n**Model:**\n", title)) FROM UNNEST(EXAMPLES)),
          "\n\n"
        ),
        "\n\n"
      ),
      ""
    ),
    "## Input\n\n",
    ARRAY_TO_STRING(
      (SELECT ARRAY_AGG(CONCAT(properties, "\n", image_info)) FROM UNNEST(PRODUCTS)),
      "\n\n"
    )
  )
);


CREATE OR REPLACE FUNCTION `[DATASET]`.DescriptionsPrompt(
  LANGUAGE STRING,
  EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>>,
  PRODUCTS ARRAY<STRUCT<properties STRING, image_info STRING>>) AS (
  CONCAT(
    "## System Instructions\n\n",
    REPLACE(
      """-- DESCRIPTIONS_PROMPT""",
      '{{LANGUAGE}}', LANGUAGE
    ),
    "\n\n",
    IF(ARRAY_LENGTH(EXAMPLES) > 0,
      CONCAT(
        "## Examples\n\n",
        ARRAY_TO_STRING(
          (SELECT ARRAY_AGG(CONCAT("**User:**\n", properties, "\n\n**Model:**\n", description)) FROM UNNEST(EXAMPLES)),
          "\n\n"
        ),
        "\n\n"
      ),
      ""
    ),
    "## Input\n\n",
    ARRAY_TO_STRING(
      (SELECT ARRAY_AGG(CONCAT(properties, "\n", image_info)) FROM UNNEST(PRODUCTS)),
      "\n\n"
    )
  )
);


CREATE OR REPLACE PROCEDURE `[DATASET].BatchedUpdateTitles`(
  ITEMS_PER_PROMPT INT64,
  LANGUAGE STRING,
  PARTS INT64,
  PART INT64,
  IDS ARRAY<STRING>,
  BUCKET_NAME STRING,
  USE_IMAGES BOOLEAN,
  DEBUG BOOLEAN)
OPTIONS(strict_mode=FALSE)  -- Don't abort if tables don't yet exist.
BEGIN
  DECLARE EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>> DEFAULT (
    SELECT ARRAY_AGG(Examples) FROM `[DATASET]`.Examples
  );
  LOOP
    IF (
      SELECT COUNT(*) = 0 AND IDS IS NULL
      FROM `[OUTPUT_TABLE]`
      WHERE title IS NULL AND tries < 3
        AND (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
    ) THEN LEAVE;
    END IF;

    -- Generate prompts
    CREATE OR REPLACE TEMP TABLE Prompts AS
    WITH
      Input AS (
        SELECT id, TO_JSON_STRING(I) AS properties, I.image_url
        FROM `[OUTPUT_TABLE]` AS O
        INNER JOIN `[DATASET]`.InputProcessing AS I USING (id)
        WHERE (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
          AND IF(IDS IS NOT NULL,
            O.id IN UNNEST(IDS),
            O.title IS NULL AND O.tries < 3)
        ORDER BY RAND()
        LIMIT 150
      )
    SELECT
      [id] AS ids,
      `[DATASET]`.TitlesPrompt(LANGUAGE, EXAMPLES, [STRUCT(properties, IF(USE_IMAGES AND image_url IS NOT NULL, CONCAT('image_url: gs://', BUCKET_NAME, '/feedgen_images/', REGEXP_EXTRACT(image_url, r'/([^/]+)$')), ''))]) AS prompt,
      IF(USE_IMAGES AND image_url IS NOT NULL, CONCAT('gs://', BUCKET_NAME, '/feedgen_images/', REGEXP_EXTRACT(image_url, r'/([^/]+)$')), NULL) AS uri
    FROM Input;

    -- Generate titles
    CREATE OR REPLACE TEMP TABLE Generated AS
    SELECT ids, ml_generate_text_llm_result AS output, ml_generate_text_status AS status
    FROM
      ML.GENERATE_TEXT(
        MODEL `[DATASET]`.GeminiModel,
        TABLE Prompts,
        STRUCT(
          0.1 AS temperature,
          2048 AS max_output_tokens,
          TRUE AS flatten_json_output));

    -- Debug: Save raw response or error status for all IDs in batch
    IF DEBUG THEN
      UPDATE `[OUTPUT_TABLE]` AS O
      SET O.raw_response_title = IFNULL(G.output, CONCAT("ERROR: ", G.status))
      FROM Generated AS G
      WHERE O.id IN UNNEST(G.ids);
    END IF;

    -- Store generated titles in output feed
    MERGE `[OUTPUT_TABLE]` AS O
    USING (
      SELECT 
        id, 
        COALESCE(
          REGEXP_EXTRACT(output, r"(?is)(?:\*\*|\*)*\s*generated title\s*:\s*(?:\*\*|\*)*\s*([^\n]+)"),
          IF(output NOT LIKE "%generated title:%", output, NULL)
        ) AS title
      FROM Generated, UNNEST(ids) AS id
    ) AS G
      ON O.id = G.id
    WHEN MATCHED THEN UPDATE SET
      O.title = IFNULL(G.title, O.title),
      O.tries = O.tries + 1,
      O.updated_at = CURRENT_TIMESTAMP();


    IF IDS IS NOT NULL THEN LEAVE;
    END IF;
  END LOOP;
END;


CREATE OR REPLACE PROCEDURE `[DATASET].BatchedUpdateDescriptions`(
  ITEMS_PER_PROMPT INT64,
  LANGUAGE STRING,
  PARTS INT64,
  PART INT64,
  IDS ARRAY<STRING>,
  BUCKET_NAME STRING,
  USE_IMAGES BOOLEAN,
  DEBUG BOOLEAN)
OPTIONS(strict_mode=FALSE)  -- Don't abort if tables don't yet exist.
BEGIN
  DECLARE EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>> DEFAULT (
    SELECT ARRAY_AGG(Examples) FROM `[DATASET]`.Examples
  );
  LOOP
    IF (
      SELECT COUNT(*) = 0 AND IDS IS NULL
      FROM `[OUTPUT_TABLE]`
      WHERE description IS NULL AND tries < 3
        AND (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
    ) THEN LEAVE;
    END IF;

    -- Generate prompts
    CREATE OR REPLACE TEMP TABLE Prompts AS
    WITH
      Input AS (
        SELECT id, TO_JSON_STRING(I) AS properties, I.image_url
        FROM `[OUTPUT_TABLE]` AS O
        INNER JOIN `[DATASET]`.InputProcessing AS I USING (id)
        WHERE (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
          AND IF(IDS IS NOT NULL,
            O.id IN UNNEST(IDS),
            O.description IS NULL AND O.tries < 3)
        ORDER BY RAND()
        LIMIT 150
      )
    SELECT
      [id] AS ids,
      `[DATASET]`.DescriptionsPrompt(LANGUAGE, EXAMPLES, [STRUCT(properties, IF(USE_IMAGES AND image_url IS NOT NULL, CONCAT('image_url: gs://', BUCKET_NAME, '/feedgen_images/', REGEXP_EXTRACT(image_url, r'/([^/]+)$')), ''))]) AS prompt,
      IF(USE_IMAGES AND image_url IS NOT NULL, CONCAT('gs://', BUCKET_NAME, '/feedgen_images/', REGEXP_EXTRACT(image_url, r'/([^/]+)$')), NULL) AS uri
    FROM Input;

    -- Generate descriptions
    CREATE OR REPLACE TEMP TABLE Generated AS
    SELECT ids, ml_generate_text_llm_result AS output, ml_generate_text_status AS status
    FROM
      ML.GENERATE_TEXT(
        MODEL `[DATASET]`.GeminiModel,
        TABLE Prompts,
        STRUCT(
          0.1 AS temperature,
          2048 AS max_output_tokens,
          TRUE AS flatten_json_output));

    -- Debug: Save raw response or error status for all IDs in batch
    IF DEBUG THEN
      UPDATE `[OUTPUT_TABLE]` AS O
      SET O.raw_response_description = IFNULL(G.output, CONCAT("ERROR: ", G.status))
      FROM Generated AS G
      WHERE O.id IN UNNEST(G.ids);
    END IF;

    -- Store generated descriptions in output feed
    MERGE `[OUTPUT_TABLE]` AS O
    USING (
      SELECT 
        id, 
        COALESCE(
          REGEXP_EXTRACT(output, r"(?is)(?:\*\*|\*)*\s*generated description\s*:\s*(?:\*\*|\*)*\s*(.*?)(?:\n\s*(?:\*\*|\*)*\s*score:|$)"),
          IF(output NOT LIKE "%generated description:%", output, NULL)
        ) AS description
      FROM Generated, UNNEST(ids) AS id
    ) AS G
      ON O.id = G.id
    WHEN MATCHED THEN UPDATE SET
      O.description = IFNULL(G.description, O.description),
      O.tries = O.tries + 1,
      O.updated_at = CURRENT_TIMESTAMP();


    IF IDS IS NOT NULL THEN LEAVE;
    END IF;
  END LOOP;
END;
