<script lang="ts">
<!--
  组件分类: 聊天组件
  功能描述: 聊天组件 - TextToken
  文件路径: src/lib/components/chat/Messages/Markdown/MarkdownInlineTokens/TextToken.svelte
-->


	export let token;
	export let done = true;
</script>

{#if done}
	{token?.raw}
{:else}
	{#each (token?.raw ?? '').split(' ') as text}
		<span class="fade-in-token">
			{text}{' '}
		</span>
	{/each}
{/if}
