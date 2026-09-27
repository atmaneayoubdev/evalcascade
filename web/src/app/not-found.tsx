import { NotFoundState } from "@/components/common/states";
import { PageHeader } from "@/components/common/layout";

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <NotFoundState detail="There is no dashboard page at this address." />
    </>
  );
}
