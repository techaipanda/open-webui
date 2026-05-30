<script lang="ts">
<!--
  组件分类: 聊天组件
  功能描述: 聊天组件 - VideoInputMenu
  文件路径: src/lib/components/chat/MessageInput/CallOverlay/VideoInputMenu.svelte
-->


	import { getContext, createEventDispatcher } from 'svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Dropdown from '$lib/components/common/Dropdown.svelte';

	export let onClose: Function = () => {};
	export let devices: any;

	let show = false;
</script>

<Dropdown
	bind:show
	side="top"
	sideOffset={6}
	onOpenChange={(state) => {
		if (state === false) {
			onClose();
		}
	}}
>
	<slot />

	<div slot="content">
		<div
			class="min-w-[180px] rounded-lg p-1 border border-gray-100 dark:border-gray-800 z-[9999] bg-white dark:bg-gray-900 dark:text-white shadow-xs"
		>
			{#each devices as device}
				<button
					class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md w-full"
					on:click={() => {
						dispatch('change', device.deviceId);
					}}
				>
					<div class="flex items-center">
						<div class=" line-clamp-1">
							{device?.label ?? 'Camera'}
						</div>
					</div>
				</button>
			{/each}
		</div>
	</div>
</Dropdown>
