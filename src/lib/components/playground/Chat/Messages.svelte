<script lang="ts">
<!--
  组件分类: Playground组件
  功能描述: Playground组件 - Messages
  文件路径: src/lib/components/playground/Chat/Messages.svelte
-->


	import { onMount, getContext } from 'svelte';
	import Message from './Message.svelte';

	const i18n = getContext('i18n');

	export let messages = [];
</script>

<div class="py-3 space-y-3">
	{#each messages as message, idx}
		<Message
			{message}
			{idx}
			onDelete={() => {
				messages = messages.filter((message, messageIdx) => messageIdx !== idx);
			}}
		/>
	{/each}
</div>
