import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => ({
	plugins: [sveltekit({ compilerOptions: { runes: true } })],
	// components mount in the tests, so they need Svelte's browser build
	resolve: mode === 'test' ? { conditions: ['browser'] } : {},
	server: { proxy: { '/api/v1': 'http://localhost:8000' } },
	test: { include: ['src/**/*.test.ts'] }
}));
