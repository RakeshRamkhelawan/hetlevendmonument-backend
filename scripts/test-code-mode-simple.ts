#!/usr/bin/env node
/**
 * Simplified Code-Mode Test
 * Tests basic initialization without MCP servers
 */

import { CodeModeUtcpClient } from '@utcp/code-mode';
import {
  InMemConcurrentToolRepositorySerializer,
  TagSearchStrategyConfigSerializer
} from '@utcp/sdk';

async function main() {
  console.log('🧪 Testing Code-Mode basic initialization...\n');

  try {
    // Test 1: Create client without manual templates
    console.log('Test 1: Create empty client...');
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
      manual_call_templates: []
    });
    console.log('✅ Client created successfully\n');

    // Test 2: Basic code execution (no tools)
    console.log('Test 2: Execute simple TypeScript code...');
    const { result, logs } = await client.callToolChain(`
      const message = 'Hello from Code-Mode!';
      console.log(message);
      return { success: true, message };
    `, 5000);

    console.log('✅ Code executed successfully');
    console.log('Result:', result);
    console.log('Logs:', logs);
    console.log('');

    // Test 3: Test with arithmetic
    console.log('Test 3: Execute arithmetic operations...');
    const { result: mathResult } = await client.callToolChain(`
      const numbers = [1, 2, 3, 4, 5];
      const sum = numbers.reduce((a, b) => a + b, 0);
      const average = sum / numbers.length;

      console.log('Sum:', sum);
      console.log('Average:', average);

      return { sum, average, count: numbers.length };
    `, 5000);

    console.log('✅ Math operations completed');
    console.log('Result:', mathResult);
    console.log('');

    // Test 4: Verify interface generation works
    console.log('Test 4: Generate TypeScript interfaces...');
    const interfaces = await client.getAllToolsTypeScriptInterfaces();
    console.log('✅ Interface generation works');
    console.log('Generated interfaces length:', interfaces.length, 'characters');
    console.log('');

    console.log('🎉 All tests passed! Code-Mode is working correctly.\n');

    console.log('📝 Summary:');
    console.log('  - Client creation: ✅');
    console.log('  - Code execution: ✅');
    console.log('  - Arithmetic operations: ✅');
    console.log('  - Interface generation: ✅');
    console.log('');
    console.log('Next step: Configure MCP servers for tool access');

  } catch (error) {
    console.error('❌ Test failed:', error);
    process.exit(1);
  }
}

// Run if executed directly
main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
