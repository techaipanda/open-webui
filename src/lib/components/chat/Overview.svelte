<script lang="ts">
<!--
  组件分类: 聊天组件
  功能描述: 聊天组件 - Overview
  文件路径: src/lib/components/chat/Overview.svelte
-->


	import { getContext, createEventDispatcher, onDestroy } from 'svelte';
	import { useSvelteFlow, useNodesInitialized, useStore, SvelteFlowProvider } from '@xyflow/svelte';

	const dispatch = createEventDispatcher();

	import View from './Overview/View.svelte';

	export let history;

	export let onClose;
	export let onNodeClick;
</script>

<SvelteFlowProvider>
	<View {history} {onClose} {onNodeClick} />
</SvelteFlowProvider>
