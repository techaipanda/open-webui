<script lang="ts">
<!--
  组件分类: 聊天组件
  功能描述: 聊天组件 - ProfileImage
  文件路径: src/lib/components/chat/Messages/ProfileImage.svelte
-->


	import { WEBUI_BASE_URL } from '$lib/constants';
	import { safeImageUrl } from '$lib/utils/safeImageUrl';

	export let className = 'size-8';
	export let src = `${WEBUI_BASE_URL}/static/favicon.png`;
</script>

<img
	aria-hidden="true"
	src={safeImageUrl(src)}
	class=" {className} object-cover rounded-full"
	alt="profile"
	draggable="false"
/>
