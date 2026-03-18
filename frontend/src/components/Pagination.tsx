type Props = {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  label?: string;
};

export default function Pagination({ page, totalPages, onPageChange, label }: Props) {
  if (totalPages <= 1) return null;

  return (
    <div className="paginationBar">
      <div className="hint">{label || `Page ${page} of ${totalPages}`}</div>
      <div className="paginationActions">
        <button className="secondaryBtn paginationBtn" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
          Previous
        </button>
        <span className="paginationCurrent">{page} / {totalPages}</span>
        <button
          className="secondaryBtn paginationBtn"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next
        </button>
      </div>
    </div>
  );
}
