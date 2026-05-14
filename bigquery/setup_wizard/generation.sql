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
  PROPERTIES ARRAY<STRING>) AS (
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
    ARRAY_TO_STRING(PROPERTIES, '\n', '')
  )
);


CREATE OR REPLACE FUNCTION `[DATASET]`.DescriptionsPrompt(
  LANGUAGE STRING,
  EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>>,
  PROPERTIES ARRAY<STRING>) AS (
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
    ARRAY_TO_STRING(PROPERTIES, '\n', '')
  )
);


CREATE OR REPLACE PROCEDURE `[DATASET].BatchedUpdateTitles`(
  ITEMS_PER_PROMPT INT64,
  LANGUAGE STRING,
  PARTS INT64,
  PART INT64,
  IDS ARRAY<STRING>)
OPTIONS(strict_mode=FALSE)  -- Don't abort if tables don't yet exist.
BEGIN
  DECLARE EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>> DEFAULT (
    SELECT ARRAY_AGG(Examples) FROM `[DATASET]`.Examples
  );
  LOOP
    IF (
      SELECT COUNT(*) = 0 AND IDS IS NULL
      FROM `[DATASET]`.Output
      WHERE title IS NULL AND tries < 3
        AND (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
    ) THEN LEAVE;
    END IF;

    -- Generate prompts
    CREATE OR REPLACE TEMP TABLE Prompts AS
    WITH
      Input AS (
        SELECT id, TO_JSON_STRING(I) AS properties
        FROM `[DATASET]`.Output AS O
        INNER JOIN `[DATASET]`.InputProcessing AS I USING (id)
        WHERE (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
          AND IF(IDS IS NOT NULL,
            O.id IN UNNEST(IDS),
            O.title IS NULL AND O.tries < 3)
        ORDER BY RAND()
        LIMIT 600 -- TODO: Find out how to use a parameter ITEMS_PER_ITERATION here.
      ),
      Numbered AS (
        SELECT id, properties, ROW_NUMBER() OVER (ORDER BY id) - 1 AS row_id
        FROM Input
      )
    SELECT
      DIV(row_id, ITEMS_PER_PROMPT) AS chunk_id,
      `[DATASET]`.TitlesPrompt(LANGUAGE, EXAMPLES, ARRAY_AGG(properties ORDER BY id)) AS prompt,
      ARRAY_AGG(id ORDER BY id) AS ids
    FROM Numbered
    GROUP BY 1;

    -- Generate titles
    CREATE OR REPLACE TEMP TABLE Generated AS
    SELECT ids, ml_generate_text_llm_result AS output
    FROM
      ML.GENERATE_TEXT(
        MODEL `[DATASET]`.GeminiModel,
        TABLE Prompts,
        STRUCT(
          0.1 AS temperature,
          2048 AS max_output_tokens,
          TRUE AS flatten_json_output));

    -- Store generated titles in output feed
    MERGE `[DATASET]`.Output AS O
    USING (
      WITH Extracted AS (
        SELECT
          REGEXP_EXTRACT(block, r'(?i)id:\s*([^\n]+)') AS id,
          REGEXP_EXTRACT(block, r'(?i)generated title:\s*([^\n]+)') AS title
        FROM Generated,
        UNNEST(REGEXP_EXTRACT_ALL(output, r'(?is)id:[^\n]+.*?generated title:[^\n]+')) AS block
      )
      SELECT id, title FROM Extracted
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id) = 1 AND id IS NOT NULL
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
  IDS ARRAY<STRING>)
OPTIONS(strict_mode=FALSE)  -- Don't abort if tables don't yet exist.
BEGIN
  DECLARE EXAMPLES ARRAY<STRUCT<id STRING, properties STRING, title STRING, description STRING>> DEFAULT (
    SELECT ARRAY_AGG(Examples) FROM `[DATASET]`.Examples
  );
  LOOP
    IF (
      SELECT COUNT(*) = 0 AND IDS IS NULL
      FROM `[DATASET]`.Output
      WHERE description IS NULL AND tries < 3
        AND (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
    ) THEN LEAVE;
    END IF;

    -- Generate prompts
    CREATE OR REPLACE TEMP TABLE Prompts AS
    WITH
      Input AS (
        SELECT id, TO_JSON_STRING(I) AS properties
        FROM `[DATASET]`.Output AS O
        INNER JOIN `[DATASET]`.InputProcessing AS I USING (id)
        WHERE (PARTS IS NULL OR ABS(MOD(FARM_FINGERPRINT(id), PARTS)) = PART)
          AND IF(IDS IS NOT NULL,
            O.id IN UNNEST(IDS),
            O.description IS NULL AND O.tries < 3)
        ORDER BY RAND()
        LIMIT 600 -- TODO: Find out how to use a parameter ITEMS_PER_ITERATION here.
      ),
      Numbered AS (
        SELECT id, properties, ROW_NUMBER() OVER (ORDER BY id) - 1 AS row_id
        FROM Input
      )
    SELECT
      DIV(row_id, ITEMS_PER_PROMPT) AS chunk_id,
      `[DATASET]`.DescriptionsPrompt(LANGUAGE, EXAMPLES, ARRAY_AGG(properties ORDER BY id)) AS prompt,
      ARRAY_AGG(id ORDER BY id) AS ids
    FROM Numbered
    GROUP BY 1;

    -- Generate descriptions
    CREATE OR REPLACE TEMP TABLE Generated AS
    SELECT ids, ml_generate_text_llm_result AS output
    FROM
      ML.GENERATE_TEXT(
        MODEL `[DATASET]`.GeminiModel,
        TABLE Prompts,
        STRUCT(
          0.1 AS temperature,
          2048 AS max_output_tokens,
          TRUE AS flatten_json_output));

    -- Store generated descriptions in output feed
    MERGE `[DATASET]`.Output AS O
    USING (
      WITH Extracted AS (
        SELECT
          REGEXP_EXTRACT(block, r'(?i)id:\s*([^\n]+)') AS id,
          REGEXP_EXTRACT(block, r'(?is)generated description:\s*(.*?)(?:\n\s*score:|$)') AS description
        FROM Generated,
        UNNEST(REGEXP_EXTRACT_ALL(output, r'(?is)id:[^\n]+.*?score:[^\n]+')) AS block
      )
      SELECT id, description FROM Extracted
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id) = 1 AND id IS NOT NULL
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

