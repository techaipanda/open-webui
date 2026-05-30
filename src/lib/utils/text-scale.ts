/**
 * 工具函数模块 - 文本缩放工具 - 响应式文本大小调整
 */


export const setTextScale = (scale) => {
	if (typeof document === 'undefined') {
		return;
	}

	document.documentElement.style.setProperty('--app-text-scale', `${scale}`);
};
