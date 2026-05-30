import { WEBUI_API_BASE_URL } from '$lib/constants';

/**
 * API 客户端模块 - 任务管理 API
 *
 * 功能说明:
 * - 异步任务状态管理
 * - 任务停止与控制
 * - 任务结果获取
 *
 * 主要API端点:
 * - /tasks/* - 任务管理操作
 */

export const checkActiveChats = async (token: string, chatIds: string[]) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/tasks/active/chats`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ chat_ids: chatIds })
	});
	if (!res.ok) throw await res.json();
	return res.json();
};
