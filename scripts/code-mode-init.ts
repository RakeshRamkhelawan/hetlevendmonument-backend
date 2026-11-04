#!/usr/bin/env node
/**
 * Code-Mode Initialization Script
 *
 * Quick-start script to initialize Code-Mode client and generate TypeScript interfaces.
 *
 * Usage:
 *   npm run code-mode-init
 *   # or
 *   node scripts/code-mode-init.ts
 */

import { CodeModeUtcpClient } from '@utcp/code-mode';
import { McpCallTemplateSerializer } from '@utcp/mcp';
import {
  InMemConcurrentToolRepositorySerializer,
  TagSearchStrategyConfigSerializer
} from '@utcp/sdk';
import { promises as fs } from 'node:fs';
import * as path from 'node:path';

async function main() {
  console.log('🤖 Initializing Code-Mode for SanskritiSetu.org...\n');

  try {
    // Step 1: Load and validate MCP configurations
    console.log('📦 Step 1: Loading and validating MCP configurations...');
    const configContent = await fs.readFile('.utcp_config.json', 'utf-8');
    const config = JSON.parse(configContent);

    // Use McpCallTemplateSerializer to validate each manual
    const mcpSerializer = new McpCallTemplateSerializer();
    const validatedManuals = config.manuals.map((manual: any) => {
      return mcpSerializer.validateDict(manual);
    });

    console.log(`✅ Validated ${validatedManuals.length} MCP manual configurations\n`);

    // Step 2: Create client instance
    console.log('🔧 Step 2: Creating Code-Mode client...');

    // Create serializers for repository and search strategy
    const toolRepository = new InMemConcurrentToolRepositorySerializer().validateDict({
      tool_repository_type: 'in_memory'
    });

    const searchStrategy = new TagSearchStrategyConfigSerializer().validateDict({
      tool_search_strategy_type: 'tag_and_description_word_match'
    });

    const client = await CodeModeUtcpClient.create('.', {
      variables: {},
      load_variables_from: null,
      tool_repository: toolRepository,
      tool_search_strategy: searchStrategy,
      post_processing: [],
      manual_call_templates: validatedManuals
    });
    console.log('✅ Client created successfully\n');

    // Step 3: Discover available tools
    console.log('🔍 Step 3: Discovering available tools...');
    const allTools = await client.searchTools('');
    console.log(`✅ Found ${allTools.length} tools across all manuals\n`);

    // Step 4: List tools by manual
    console.log('📋 Step 4: Available tool manuals:');
    const manuals = ['filesystem', 'github', 'postgres'];
    for (const manual of manuals) {
      const tools = await client.searchTools(manual);
      console.log(`  - ${manual}: ${tools.length} tools`);
    }
    console.log('');

    // Step 5: Generate TypeScript interfaces
    console.log('🔧 Step 5: Generating TypeScript interfaces...');
    const interfaces = await client.getAllToolsTypeScriptInterfaces();
    const interfacesPath = path.join(process.cwd(), 'generated-tools.d.ts');
    await fs.writeFile(interfacesPath, interfaces);
    console.log(`✅ TypeScript interfaces saved to: generated-tools.d.ts\n`);

    // Step 6: Test simple tool chain
    console.log('🧪 Step 6: Running test tool chain...');
    try {
      const testResult = await client.callToolChain(`
        // Simple test: list current directory using generated-tool API
        const files = await filesystem.filesystem_list_directory({ path: '.' });

        console.log('Current directory files:', Array.isArray(files) ? files.length : 0);

        return {
          success: true,
          filesFound: Array.isArray(files) ? files.length : 0,
          raw: files,
          timestamp: new Date().toISOString()
        };
      `, 10000); // 10 second timeout

      console.log('✅ Test tool chain executed successfully');
      console.log('📊 Result:', JSON.stringify(testResult.result, null, 2));
      console.log('📝 Logs:', testResult.logs.join('\n'));
      console.log('');
    } catch (error) {
      console.warn('⚠️  Test tool chain skipped (MCP servers may not be running)');
      console.warn('   This is expected on first setup. Run Docker services first.\n');
    }

    // Step 7: Display usage instructions
    console.log('📚 Step 7: Next steps:');
    console.log(`
  1. Start Docker services:
     docker-compose -f docker-compose.dev.yml up -d

  2. Use Code-Mode in your AI prompts:
     import { codeAgent } from './scripts/code-mode-agent';
     // Use codeAgent as system prompt

  3. Example tool chain execution:
     const result = await client.callToolChain(\`
       const files = await filesystem.read_file('README.md');
       return { content: files };
     \`);

  4. Update tsconfig.json to include generated interfaces:
     {
       "compilerOptions": {
         "typeRoots": ["./generated-tools.d.ts"]
       }
     }

  5. Read the integration guide:
     .github/AI_AGENT_CODE_MODE_INTEGRATION.md
`);

    console.log('✅ Code-Mode initialization complete!\n');

  } catch (error) {
    console.error('❌ Initialization failed:', error);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}
