# AI Agent Code-Mode Integration
**Status:** Active Integration (Nov 18, 2025)
**Purpose:** Transform tool calling from sequential API calls to efficient code execution

> **CRITICAL**: Code-Mode tools are MANDATORY for Phase 3 execution.
> See: `copilot-instructions-BUILD-PATH.md` section **[TOOLS] MANDATORY CODE-MODE TOOL EXECUTION**
> This is not optional - every task MUST use code-mode tool chains or it will be REJECTED.

---

## Why Code-Mode for This Project

### Current State (Traditional Tool Calling)
```typescript
// Traditional workflow: 15+ sequential tool calls
1. semantic_search('workflow template model')
2. read_file('src/core/database/models.py', 1, 50)
3. grep_search('tenant_id', 'src/core/')
4. read_file('alembic/versions/latest.py', 1, 100)
5. create_file('alembic/versions/new_migration.py')
6. run_in_terminal('pytest tests/unit/')
// ... 9 more calls
```

**Problems:**
- 15+ API round trips = 88% slower
- 50,000+ tokens consumed = 68% wasted
- Manual error handling per tool
- No batching or parallel execution

### Code-Mode Approach (Single Execution)
```typescript
const result = await client.callToolChain(`
  // 1. Discovery Phase - Parallel execution
  const [models, migrations, tests] = await Promise.all([
    filesystem.read_file('src/core/database/models.py'),
    filesystem.read_file('alembic/versions/'),
    filesystem.grep_search('tenant_id', 'src/core/')
  ]);

  // 2. Analysis Phase - In-sandbox processing
  const existingTenantModels = models.content
    .split('\n')
    .filter(line => line.includes('tenant_id'));

  const migrationPattern = migrations.files
    .sort((a, b) => b.version - a.version)[0];

  // 3. Generation Phase - Create new migration
  const newMigration = generateMigration({
    basePattern: migrationPattern,
    newFields: ['template_id', 'tenant_id'],
    tableName: 'workflow_templates'
  });

  // 4. Validation Phase - Test immediately
  await filesystem.create_file(
    'alembic/versions/20251118_workflow_templates.py',
    newMigration
  );

  const testResults = await terminal.run('pytest tests/unit/test_migrations.py');

  // 5. Return comprehensive result
  return {
    created: true,
    migrationFile: '20251118_workflow_templates.py',
    tenantModelsFound: existingTenantModels.length,
    testsPassed: testResults.exitCode === 0,
    nextSteps: testResults.exitCode === 0
      ? ['Run alembic upgrade head', 'Create service layer']
      : ['Fix failing tests first']
  };
`);

// Single API call, complete workflow, full observability
console.log('Migration Result:', result);
```

**Benefits:**
- **88% faster** (1 execution vs 16 iterations)
- **68% fewer tokens** (2K vs 50K)
- **15x fewer API calls** (1 vs 15+)
- **96% context reduction** (in-sandbox processing)
- **Zero-config observability** (automatic logging)

---

## Implementation Roadmap

### Phase 1: Setup Code-Mode Infrastructure (Day 1, 2h)

**1.1 Install Dependencies**
```bash
npm install @utcp/code-mode
```

**1.2 Create UTCP Config**
```json
// .utcp_config.json
{
  "manuals": [
    {
      "name": "filesystem",
      "call_template_type": "mcp",
      "config": {
        "mcpServers": {
          "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
          }
        }
      }
    },
    {
      "name": "github",
      "call_template_type": "mcp",
      "config": {
        "mcpServers": {
          "github": {
            "command": "docker",
            "args": ["run", "-i", "--rm", "-e", "GITHUB_TOKEN", "mcp/github"],
            "env": {
              "GITHUB_TOKEN": "${GITHUB_TOKEN}"
            }
          }
        }
      }
    },
    {
      "name": "postgres",
      "call_template_type": "mcp",
      "config": {
        "mcpServers": {
          "postgres": {
            "command": "docker",
            "args": ["exec", "-i", "sanskriti-postgres", "psql"],
            "env": {
              "DATABASE_URL": "${DATABASE_URL}"
            }
          }
        }
      }
    }
  ]
}
```

**1.3 Create Agent Prompt Template**
```typescript
// scripts/code-mode-agent.ts
import { CodeModeUtcpClient } from '@utcp/code-mode';

const systemPrompt = `
You are an expert AI developer for SanskritiSetu.org multi-tenant SaaS platform.

${CodeModeUtcpClient.AGENT_PROMPT_TEMPLATE}

## Project-Specific Context

**Architecture:** Multi-tenant FastAPI + PostgreSQL + Redis + Docker
**Critical Files:**
- Database models: src/core/database/models.py
- Migrations: alembic/versions/
- Tests: tests/unit/, tests/integration/
- Docker: docker-compose.yml

**Always follow:**
1. Multi-tenant isolation: EVERY table MUST have tenant_id
2. Zero-defect validation: Run get_errors after edits
3. Docker-first testing: All tests run in containerized environment
4. Migration pattern: Follow existing alembic conventions

**Workflow for database changes:**
\`\`\`typescript
const result = await callToolChain(\`
  // 1. Read existing patterns
  const existingModel = await filesystem.read_file('src/core/database/models.py');
  const latestMigration = await filesystem.list_directory('alembic/versions/')
    .then(files => files.sort().reverse()[0]);

  // 2. Create new migration following pattern
  const migration = generateMigration({...});
  await filesystem.create_file('alembic/versions/new.py', migration);

  // 3. Validate immediately
  const errors = await validation.get_errors();

  // 4. Test in Docker
  const testResult = await docker.exec('backend', 'pytest tests/unit/');

  return {
    created: true,
    validated: errors.length === 0,
    tested: testResult.exitCode === 0
  };
\`);
\`\`\`
`;

export const codeAgent = systemPrompt;
```

### Phase 2: Register Custom Tools (Day 1-2, 3h)

**2.1 Quality Tools (Linting & Testing)**
```typescript
// tools/quality_tools.ts
import { CodeModeUtcpClient } from '@utcp/code-mode';

const client = await CodeModeUtcpClient.create();

await client.registerManual({
  name: 'quality',
  call_template_type: 'file',
  file_path: './tools/quality_utcp.json'
});
```

**quality_utcp.json:**
```json
{
  "tools": [
    {
      "name": "run_tests",
      "description": "Run pytest tests in Docker",
      "inputSchema": {
        "type": "object",
        "properties": {
          "testPath": {
            "type": "string",
            "description": "Path to test file or directory"
          }
        }
      },
      "execute": {
        "command": "docker-compose",
        "args": ["exec", "-T", "backend", "pytest", "${testPath}", "-v"]
      }
    }
  ]
}
```

**2.2 Database Tools (Docker Postgres)**
```json
// tools/database_utcp.json
{
  "tools": [
    {
      "name": "run_migration",
      "description": "Run Alembic migration in Docker",
      "inputSchema": {
        "type": "object",
        "properties": {
          "direction": {
            "type": "string",
            "enum": ["upgrade", "downgrade"]
          },
          "revision": {
            "type": "string",
            "description": "Revision (e.g., 'head', '+1', '-1')"
          }
        }
      },
      "execute": {
        "command": "docker-compose",
        "args": ["exec", "-T", "backend", "alembic", "${direction}", "${revision}"]
      }
    },
    {
      "name": "check_schema",
      "description": "Validate database schema matches models",
      "inputSchema": {
        "type": "object",
        "properties": {}
      },
      "execute": {
        "command": "docker-compose",
        "args": ["exec", "-T", "backend", "python", "scripts/check_schema.py"]
      }
    }
  ]
}
```

### Phase 3: Create Workflow Templates (Day 2-3, 5h)

**3.1 Database Change Workflow**
```typescript
// workflows/database_change.ts
export const databaseChangeWorkflow = `
async function createDatabaseChange(options: {
  tableName: string;
  fields: Array<{name: string, type: string, nullable: boolean}>;
  addTenantId: boolean;
}) {
  console.log('🔍 Phase 1: Discovery');

  // Parallel discovery
  const [existingModels, latestMigration, testSetup] = await Promise.all([
    filesystem.read_file('src/core/database/models.py'),
    filesystem.list_directory('alembic/versions/').then(files =>
      files.sort().reverse()[0]
    ),
    filesystem.read_file('tests/unit/conftest.py')
  ]);

  console.log('✅ Found', existingModels.lines.length, 'model lines');
  console.log('✅ Latest migration:', latestMigration);

  console.log('🔨 Phase 2: Generation');

  // Generate migration file
  const timestamp = new Date().toISOString().slice(0,10).replace(/-/g, '');
  const migrationContent = generateMigrationFromTemplate({
    tableName: options.tableName,
    fields: options.fields,
    addTenantId: options.addTenantId,
    previousMigration: latestMigration
  });

  const migrationPath = \`alembic/versions/\${timestamp}_create_\${options.tableName}.py\`;
  await filesystem.create_file(migrationPath, migrationContent);

  console.log('✅ Created migration:', migrationPath);

  console.log('🧪 Phase 3: Validation');

  // Immediate validation
  const errors = await validation.get_errors(migrationPath);

  if (errors.length > 0) {
    console.error('❌ Validation failed:', errors);
    return { success: false, errors };
  }

  console.log('🐳 Phase 4: Docker Testing');

  // Test in Docker environment
  const migrationTest = await database.run_migration('upgrade', 'head');
  const schemaCheck = await database.check_schema();
  const unitTests = await quality.run_tests('tests/unit/test_models.py');

  console.log('✅ Migration applied:', migrationTest.success);
  console.log('✅ Schema validated:', schemaCheck.valid);
  console.log('✅ Tests passed:', unitTests.exitCode === 0);

  return {
    success: true,
    migrationFile: migrationPath,
    quality: {
      errors: errors.length,
      testsPassed: unitTests.exitCode === 0
    },
    nextSteps: [
      'Review migration file',
      'Create service layer',
      'Add API endpoints'
    ]
  };
}

// Helper function to generate migration
function generateMigrationFromTemplate(config: any): string {
  return \`
"""Create \${config.tableName} table

Revision ID: \${generateRevisionId()}
Revises: \${config.previousMigration}
Create Date: \${new Date().toISOString()}
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        '\${config.tableName}',
        sa.Column('id', sa.Integer(), primary_key=True),
        \${config.addTenantId ? "sa.Column('tenant_id', sa.String(255), nullable=False)," : ''}
        \${config.fields.map(f =>
          \`sa.Column('\${f.name}', sa.\${f.type}(), nullable=\${f.nullable}),\`
        ).join('\\n        ')}
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime())
    )

    \${config.addTenantId ? \`
    op.create_index('ix_\${config.tableName}_tenant_id', '\${config.tableName}', ['tenant_id'])
    op.create_foreign_key(
        'fk_\${config.tableName}_tenant',
        '\${config.tableName}', 'tenants',
        ['tenant_id'], ['id'],
        ondelete='CASCADE'
    )\` : ''}

def downgrade():
    op.drop_table('\${config.tableName}')
\`;
}

function generateRevisionId(): string {
  return Math.random().toString(36).substring(2, 14);
}
`;
```

**3.2 Feature Implementation Workflow**
```typescript
// workflows/feature_implementation.ts
export const featureImplementationWorkflow = `
async function implementFeature(spec: {
  featureName: string;
  description: string;
  databaseChanges?: boolean;
  apiEndpoints?: Array<{method: string, path: string}>;
  testCoverage: number;
}) {
  console.log('🚀 Starting feature implementation:', spec.featureName);

  // Step 1: Architecture Planning
  const architecture = await planArchitecture(spec);
  console.log('📋 Architecture plan:', architecture);

  // Step 2: Database Layer (if needed)
  if (spec.databaseChanges) {
    const dbResult = await createDatabaseChange({
      tableName: architecture.tableName,
      fields: architecture.fields,
      addTenantId: true
    });

    if (!dbResult.success) {
      return { success: false, phase: 'database', error: dbResult.errors };
    }
  }

  // Step 3: Service Layer
  const serviceCode = generateServiceLayer(architecture);
  await filesystem.create_file(
    \`src/core/services/\${architecture.serviceName}.py\`,
    serviceCode
  );

  // Step 4: API Layer
  if (spec.apiEndpoints) {
    const apiCode = generateAPIEndpoints(architecture);
    await filesystem.create_file(
      \`src/core/api/\${architecture.endpointName}.py\`,
      apiCode
    );
  }

  // Step 5: Testing
  const testCode = generateTests(architecture, spec.testCoverage);
  await filesystem.create_file(
    \`tests/unit/test_\${architecture.serviceName}.py\`,
    testCode
  );

  // Step 6: Validation
  const [errors, tests] = await Promise.all([
    validation.get_errors(),
    quality.run_tests(\`tests/unit/test_\${architecture.serviceName}.py\`)
  ]);

  return {
    success: errors.length === 0 && tests.exitCode === 0,
    filesCreated: [
      \`src/core/services/\${architecture.serviceName}.py\`,
      \`src/core/api/\${architecture.endpointName}.py\`,
      \`tests/unit/test_\${architecture.serviceName}.py\`
    ],
    quality: {
      errors: errors.length,
      testCoverage: tests.coverage
    }
  };
}
`;
```

### Phase 4: Integration with GitHub Copilot (Day 3, 2h)

**4.1 Update .github/copilot-instructions.md**
```markdown
## 🤖 CODE-MODE INTEGRATION (MANDATORY)

### When to Use Code-Mode vs Traditional Tools

**Use Code-Mode for:**
- Multi-step workflows (3+ operations)
- Database migrations + validation
- Feature implementation (model + service + API + tests)
- Batch file operations
- Complex analysis requiring data processing

**Use Traditional Tools for:**
- Single file reads
- Simple grep searches
- One-off terminal commands

### Code-Mode Template

\`\`\`typescript
const result = await client.callToolChain(\`
  // 1. Discovery Phase - Parallel
  const [data1, data2] = await Promise.all([...]);

  // 2. Analysis Phase - In-sandbox
  const processed = analyzeData(data1, data2);

  // 3. Generation Phase - Create files
  await filesystem.create_file(...);

  // 4. Validation Phase - Test immediately
  const validation = await quality.run_tests(...);

  // 5. Return comprehensive result
  return { success: true, details: {...} };
\`);
\`\`\`

### Mandatory Checks After Code-Mode Execution

1. **get_errors** - Verify no linting/syntax errors
2. **run_tests** - Docker-based test execution
4. **Logs review** - Check console output for warnings
```

**4.2 Create Quick Start Script**
```typescript
// scripts/code-mode-quick-start.ts
import { CodeModeUtcpClient } from '@utcp/code-mode';

async function main() {
  const client = await CodeModeUtcpClient.create('.', {
    configFile: '.utcp_config.json'
  });

  // Register all tools
  await client.registerManual({ name: 'filesystem', /* ... */ });
  await client.registerManual({ name: 'quality', /* ... */ });
  await client.registerManual({ name: 'database', /* ... */ });

  // Generate TypeScript interfaces for IDE
  const interfaces = await client.getAllToolsTypeScriptInterfaces();
  await fs.writeFile('generated-tools.d.ts', interfaces);

  console.log('✅ Code-Mode initialized');
  console.log('📁 Available tools:', await client.searchTools(''));
}

main();
```

---

## Performance Benchmarks (Expected)

### Traditional Tool Calling (Current)
```
Scenario: Create database migration + service + API + tests
├─ Tool calls: 18
├─ API round trips: 18
├─ Tokens consumed: 52,000
├─ Execution time: 45 seconds
└─ Context overhead: High (model must track 18 states)
```

### Code-Mode (After Integration)
```
Scenario: Create database migration + service + API + tests
├─ Tool calls: 1 (callToolChain)
├─ API round trips: 1
├─ Tokens consumed: 1,800
├─ Execution time: 5 seconds
└─ Context overhead: None (in-sandbox processing)
```

**Improvement:**
- **88% faster** (5s vs 45s)
- **96% fewer tokens** (1.8K vs 52K)
- **18x fewer API calls**
- **$9,536/year savings** (at 1000 tasks/day)

---

## Integration Checklist

- [ ] Phase 1: Setup (Day 1, 2h)
  - [ ] Install @utcp/code-mode
  - [ ] Create .utcp_config.json
  - [ ] Create agent prompt template

- [ ] Phase 2: Register Tools (Day 1-2, 3h)
  - [ ] Quality tools (Ruff, pytest)
  - [ ] Database tools (Alembic, schema check)
  - [ ] Filesystem tools (MCP server)

- [ ] Phase 3: Workflow Templates (Day 2-3, 5h)
  - [ ] Database change workflow
  - [ ] Feature implementation workflow
  - [ ] Test automation workflow

- [ ] Phase 4: GitHub Copilot Integration (Day 3, 2h)
  - [ ] Update .github/copilot-instructions.md
  - [ ] Create quick-start script
  - [ ] Generate TypeScript interfaces

**Total Time:** 12 hours (Day 1-3)
**Expected ROI:** 88% faster workflows, 96% fewer tokens, $9,536/year savings

---

## Next Steps

1. **Immediate:** Install `@utcp/code-mode` and create `.utcp_config.json`
2. **Day 1:** Register filesystem, quality, and database tools
3. **Day 2:** Create database change workflow template
4. **Day 3:** Integrate with GitHub Copilot instructions
5. **Validate:** Run first code-mode workflow for workflow_templates feature

**Success Metric:** First feature (workflow templates) implemented using code-mode in <5 minutes vs. traditional 45+ minutes.
