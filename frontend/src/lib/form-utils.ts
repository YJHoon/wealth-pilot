/** 폼 입력값을 숫자로 변환. 빈 값 또는 유효하지 않은 값은 undefined 반환 */
export const toNumber = (val: unknown): number | undefined => {
  if (val === "" || val === undefined || val === null) return undefined;
  const n = Number(val);
  return isNaN(n) ? undefined : n;
};
