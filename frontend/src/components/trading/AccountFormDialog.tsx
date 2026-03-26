"use client";

import { useEffect } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { toNumber as toNum } from "@/lib/form-utils";
import type { TradingMode, TradingAccountCreateRequest } from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";

interface AccountFormValues {
  mode: TradingMode;
  initial_capital: number | undefined;
}

const schema = z.object({
  mode: z.enum(["paper", "live"]),
  initial_capital: z.preprocess(
    toNum,
    z.number({ message: "숫자를 입력해주세요" }).positive("초기자금은 0보다 커야 합니다"),
  ),
});

interface AccountFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: TradingAccountCreateRequest) => Promise<void>;
  isSubmitting: boolean;
}

export function AccountFormDialog({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: AccountFormDialogProps) {
  const form = useForm<AccountFormValues>({
    resolver: zodResolver(schema) as Resolver<AccountFormValues>,
    defaultValues: {
      mode: "paper",
      initial_capital: undefined,
    },
  });

  useEffect(() => {
    if (open) {
      form.reset();
    }
  }, [open, form]);

  const handleSubmit = form.handleSubmit(async (values) => {
    await onSubmit({
      mode: values.mode,
      initial_capital: values.initial_capital!,
    });
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>매매 계좌 등록</DialogTitle>
          <DialogDescription>
            투자 모드와 초기자금을 설정합니다. KIS API 인증정보는 서버 환경변수에서 관리됩니다.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label>투자 모드</Label>
            <Select
              value={form.watch("mode")}
              onValueChange={(val) => {
                if (val) form.setValue("mode", val as TradingMode);
              }}
            >
              <SelectTrigger className="w-full">
                <span>{tradingModeLabels[form.watch("mode")]}</span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="paper">모의투자</SelectItem>
                <SelectItem value="live">실전</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="initial_capital">초기자금 (원)</Label>
            <Input
              id="initial_capital"
              type="number"
              step="any"
              placeholder="10,000,000"
              {...form.register("initial_capital")}
            />
            {form.formState.errors.initial_capital && (
              <p className="text-xs text-destructive">
                {form.formState.errors.initial_capital.message}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              취소
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "등록 중..." : "등록"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
