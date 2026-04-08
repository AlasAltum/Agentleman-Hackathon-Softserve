import {
  AbstractPaymentProvider,
  MedusaError,
  PaymentActions,
  PaymentSessionStatus,
} from "@medusajs/framework/utils"
import type {
  CapturePaymentInput,
  AuthorizePaymentInput,
  CancelPaymentInput,
  InitiatePaymentInput,
  DeletePaymentInput,
  GetPaymentStatusInput,
  RefundPaymentInput,
  RetrievePaymentInput,
  UpdatePaymentInput,
  CapturePaymentOutput,
  AuthorizePaymentOutput,
  CancelPaymentOutput,
  InitiatePaymentOutput,
  DeletePaymentOutput,
  GetPaymentStatusOutput,
  RefundPaymentOutput,
  RetrievePaymentOutput,
  UpdatePaymentOutput,
  WebhookActionResult,
} from "@medusajs/framework/types"
import crypto from "crypto"

/**
 * =========================================================================
 * STUB PAYMENT CONFIGURATION
 * =========================================================================
 * Toggle this object to simulate different payment scenarios during testing.
 *
 * To succeed:
 *   set `shouldFail: false`
 *
 * To fail:
 *   set `shouldFail: true`
 *   Then modify `errorConfig` to simulate specific error scenarios.
 *
 * Available error types:
 *   - "authorization": Fails during payment authorization (checkout)
 *   - "capture": Fails during payment capture
 *   - "refund": Fails during refund processing
 */
export const STUB_PAYMENT_CONFIG = {
  shouldFail: true,
  
  errorConfig: {
    // Which operation should fail: "authorization" | "capture" | "refund"
    failOn: "authorization" as "authorization" | "capture" | "refund",
    
    // Error details
    code: "payment_declined",
    message: "Payment was declined. This is a stub error for testing.",
  },
  
  // Delay in milliseconds to simulate network latency (0 = no delay)
  simulatedDelay: 0,
}

class StubPaymentProviderService extends AbstractPaymentProvider<Record<string, unknown>> {
  static identifier = "stub"

  constructor(container: Record<string, unknown>, config: Record<string, unknown>) {
    super(container, config)
  }

  private async simulateDelay(): Promise<void> {
    if (STUB_PAYMENT_CONFIG.simulatedDelay > 0) {
      await new Promise((resolve) => 
        setTimeout(resolve, STUB_PAYMENT_CONFIG.simulatedDelay)
      )
    }
  }

  private shouldFailOn(operation: "authorization" | "capture" | "refund"): boolean {
    return (
      STUB_PAYMENT_CONFIG.shouldFail && 
      STUB_PAYMENT_CONFIG.errorConfig.failOn === operation
    )
  }

  private throwConfiguredError(): never {
    throw new MedusaError(
      MedusaError.Types.NOT_ALLOWED,
      STUB_PAYMENT_CONFIG.errorConfig.message,
      STUB_PAYMENT_CONFIG.errorConfig.code
    )
  }

  async capturePayment(input: CapturePaymentInput): Promise<CapturePaymentOutput> {
    await this.simulateDelay()

    if (this.shouldFailOn("capture")) {
      this.throwConfiguredError()
    }

    return {
      data: {
        id: input.data?.id as string,
        status: "captured",
      },
    }
  }

  async authorizePayment(input: AuthorizePaymentInput): Promise<AuthorizePaymentOutput> {
    await this.simulateDelay()

    // This is called when the user clicks "Place Order"
    // Throwing an error here prevents the cart from completing
    if (this.shouldFailOn("authorization")) {
      this.throwConfiguredError()
    }

    return {
      status: PaymentSessionStatus.AUTHORIZED,
      data: {
        id: crypto.randomUUID(),
        status: "authorized",
      },
    }
  }

  async cancelPayment(input: CancelPaymentInput): Promise<CancelPaymentOutput> {
    await this.simulateDelay()

    return {
      data: {
        id: input.data?.id as string,
        status: "canceled",
      },
    }
  }

  async initiatePayment(input: InitiatePaymentInput): Promise<InitiatePaymentOutput> {
    await this.simulateDelay()

    // Called when the user selects this payment provider
    return {
      id: crypto.randomUUID(),
      data: {
        id: crypto.randomUUID(),
        status: "initiated",
      },
    }
  }

  async deletePayment(input: DeletePaymentInput): Promise<DeletePaymentOutput> {
    await this.simulateDelay()

    return {
      data: {
        id: (input.data?.id as string) || crypto.randomUUID(),
        status: "deleted",
      },
    }
  }

  async getPaymentStatus(input: GetPaymentStatusInput): Promise<GetPaymentStatusOutput> {
    return { status: PaymentSessionStatus.AUTHORIZED }
  }

  async refundPayment(input: RefundPaymentInput): Promise<RefundPaymentOutput> {
    await this.simulateDelay()

    if (this.shouldFailOn("refund")) {
      this.throwConfiguredError()
    }

    return {
      data: {
        id: input.data?.id as string,
        status: "refunded",
        amount: input.amount,
      },
    }
  }

  async retrievePayment(input: RetrievePaymentInput): Promise<RetrievePaymentOutput> {
    return {
      data: {
        id: input.data?.id as string,
        status: "authorized",
      },
    }
  }

  async updatePayment(input: UpdatePaymentInput): Promise<UpdatePaymentOutput> {
    return {
      data: {
        ...input.data,
      },
    }
  }

  async getWebhookActionAndData(payload: Record<string, unknown>): Promise<WebhookActionResult> {
    return {
      action: PaymentActions.NOT_SUPPORTED,
    }
  }
}

export default StubPaymentProviderService
