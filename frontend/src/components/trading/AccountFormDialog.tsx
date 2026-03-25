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
  app_key: string;
  app_secret: string;
  account_number: string;
  account_product_code: string;
  initial_capital: number | undefined;
}

const schema = z.object({
  mode: z.enum(["paper", "live"]),
  app_key: z.string().min(1, "APP Key를 입력해주세요"),
  app_secret: z.string().min(1, "APP Secret을 입력해주세요"),
  account_number: z.string().min(1, "계좌번호를 입력해주세요"),
  account_product_code: z.string().max(2).default("01"),
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
      app_key: "",
      app_secret: "",
      account_number: "",
      account_product_code: "01",
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
      app_key: values.app_key,
      app_secret: values.app_secret,
      account_number: values.account_number,
      account_product_code: values.account_product_code,
      initial_capital: values.initial_capital!,
    });
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>KIS 계좌 등록</DialogTitle>
          <DialogDescription>
            한국투자증권 API 인증정보를 입력합니다. 암호화되어 저장됩니다.
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
            <Label htmlFor="app_key">APP Key</Label>
            <Input
              id="app_key"
              type="password"
              autoComplete="off"
              {...form.register("app_key")}
            />
            {form.formState.errors.app_key && (
              <p className="text-xs text-destructive">{form.formState.errors.app_key.message}</p>
            )}
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="app_secret">APP Secret</Label>
            <Input
              id="app_secret"
              type="password"
              autoComplete="off"
              {...form.register("app_secret")}
            />
            {form.formState.errors.app_secret && (
              <p className="text-xs text-destructive">{form.formState.errors.app_secret.message}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="account_number">계좌번호</Label>
              <Input
                id="account_number"
                placeholder="50123456-01"
                {...form.register("account_number")}
              />
              {form.formState.errors.account_number && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.account_number.message}
                </p>
              )}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="account_product_code">상품코드</Label>
              <Input
                id="account_product_code"
                placeholder="01"
                maxLength={2}
                {...form.register("account_product_code")}
              />
            </div>
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
