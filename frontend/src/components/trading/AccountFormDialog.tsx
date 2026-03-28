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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import type { TradingMode, TradingAccountCreateRequest } from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";

interface AccountFormValues {
  mode: TradingMode;
}

const schema = z.object({
  mode: z.enum(["paper", "live"]),
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
    });
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>매매 계좌 등록</DialogTitle>
          <DialogDescription>
            등록 시 선택한 투자 모드로 KIS API에서 계좌 잔액을 자동으로 조회합니다.
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
