import React, { useEffect, useMemo, useRef, useState } from "react";
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

function deepCloneContainers(items) {
  return (items || []).map((container) => ({
    ...container,
    items: [...(container.items || [])],
  }));
}

function findContainerIndex(containers, itemId) {
  return containers.findIndex((container) => (container.items || []).some((item) => item.id === itemId));
}

function getItemById(containers, itemId) {
  for (const container of containers) {
    const match = (container.items || []).find((item) => item.id === itemId);
    if (match) {
      return match;
    }
  }
  return null;
}

function buildPayload(event, containers, itemId = "") {
  return {
    event,
    itemId,
    eventId: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    containers,
  };
}

function BoardCard({ item, suppressClickRef, onCardClick, onClaimClick }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const handleClick = () => {
    if (suppressClickRef.current) {
      return;
    }
    onCardClick(item.id);
  };

  const handleKeyDown = (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    handleClick();
  };

  const handleClaimClick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    onClaimClick(item.id);
  };

  const stopDragPropagation = (event) => {
    event.stopPropagation();
  };

  return (
    <div
      ref={setNodeRef}
      className={`failure-card ${isDragging ? "dragging" : ""}`}
      style={style}
      {...attributes}
      {...listeners}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
    >
      <div className="failure-card-top">
        <div className="failure-card-title">{item.title}</div>
        <div className="failure-card-actions">
          <button
            className={`assignee-badge ${item.assignee ? "filled" : ""}`}
            onClick={handleClaimClick}
            onPointerDown={stopDragPropagation}
            title={item.assignee ? `Assinado por ${item.assignee}` : "Assinar ticket"}
            type="button"
          >
            {item.assigneeInitials || "+"}
          </button>
          <div className="drag-handle" aria-hidden="true">
            ::
          </div>
        </div>
      </div>
      <div className="failure-card-content">
        <div className="failure-card-summary">{item.summary}</div>
        <div className="failure-card-meta">{item.meta}</div>
      </div>
    </div>
  );
}

function Lane({ container, suppressClickRef, onCardClick, onClaimClick }) {
  const { setNodeRef } = useDroppable({ id: container.id });
  const itemIds = (container.items || []).map((item) => item.id);

  return (
    <div className={`lane-shell lane-${String(container.id || "").toLowerCase()}`} ref={setNodeRef}>
      <div className={`lane-header lane-header-${String(container.id || "").toLowerCase()}`}>{container.header}</div>
      <SortableContext items={itemIds} strategy={rectSortingStrategy}>
        <div className="lane-body">
          {(container.items || []).map((item) => (
            <BoardCard
              key={item.id}
              item={item}
              suppressClickRef={suppressClickRef}
              onCardClick={onCardClick}
              onClaimClick={onClaimClick}
            />
          ))}
        </div>
      </SortableContext>
    </div>
  );
}

function FailureBoardComponent(props) {
  const args = props?.args ?? {};
  const itemsArg = args.items ?? [];
  const initialItems = useMemo(() => deepCloneContainers(itemsArg), [itemsArg]);
  const [containers, setContainers] = useState(initialItems);
  const [activeId, setActiveId] = useState(null);
  const rootRef = useRef(null);
  const suppressClickRef = useRef(false);

  const syncFrameHeight = () => {
    window.requestAnimationFrame(() => {
      const rootHeight = rootRef.current?.scrollHeight ?? 0;
      const documentHeight = document.documentElement?.scrollHeight ?? 0;
      const nextHeight = Math.max(rootHeight, documentHeight, 0) + 6;
      if (nextHeight > 0) {
        Streamlit.setFrameHeight(nextHeight);
      }
    });
  };

  useEffect(() => {
    setContainers(deepCloneContainers(itemsArg));
  }, [itemsArg]);

  useEffect(() => {
    syncFrameHeight();
  }, [containers, activeId]);

  useEffect(() => {
    if (!rootRef.current || typeof ResizeObserver === "undefined") {
      syncFrameHeight();
      return undefined;
    }

    const observer = new ResizeObserver(() => {
      syncFrameHeight();
    });
    observer.observe(rootRef.current);

    return () => {
      observer.disconnect();
    };
  }, []);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const activeItem = activeId ? getItemById(containers, activeId) : null;

  const pushValue = (payload) => {
    Streamlit.setComponentValue(payload);
    syncFrameHeight();
  };

  const handleCardClick = (itemId) => {
    pushValue(buildPayload("click", containers, itemId));
  };

  const handleClaimClick = (itemId) => {
    pushValue(buildPayload("claim", containers, itemId));
  };

  const handleDragStart = (event) => {
    suppressClickRef.current = true;
    setActiveId(event.active.id);
  };

  const releaseClickSuppression = () => {
    window.setTimeout(() => {
      suppressClickRef.current = false;
    }, 420);
  };

  const handleDragCancel = () => {
    setActiveId(null);
    releaseClickSuppression();
  };

  const handleDragOver = (event) => {
    const { active, over } = event;
    if (!over) {
      return;
    }

    const overIsContainer = containers.some((container) => container.id === over.id);
    const activeContainerIndex = findContainerIndex(containers, active.id);
    const overContainerIndex = overIsContainer
      ? containers.findIndex((container) => container.id === over.id)
      : findContainerIndex(containers, over.id);

    if (activeContainerIndex < 0 || overContainerIndex < 0 || activeContainerIndex === overContainerIndex) {
      return;
    }

    const nextContainers = deepCloneContainers(containers);
    const sourceItems = nextContainers[activeContainerIndex].items;
    const activeItemIndex = sourceItems.findIndex((item) => item.id === active.id);
    if (activeItemIndex < 0) {
      return;
    }

    const [movedItem] = sourceItems.splice(activeItemIndex, 1);
    const targetItems = nextContainers[overContainerIndex].items;

    if (overIsContainer) {
      targetItems.push(movedItem);
    } else {
      const overIndex = targetItems.findIndex((item) => item.id === over.id);
      targetItems.splice(overIndex >= 0 ? overIndex : targetItems.length, 0, movedItem);
    }

    setContainers(nextContainers);
  };

  const handleDragEnd = (event) => {
    const { active, over } = event;
    setActiveId(null);

    if (!over) {
      releaseClickSuppression();
      return;
    }

    const overIsContainer = containers.some((container) => container.id === over.id);
    const activeContainerIndex = findContainerIndex(containers, active.id);
    const overContainerIndex = overIsContainer
      ? containers.findIndex((container) => container.id === over.id)
      : findContainerIndex(containers, over.id);

    if (activeContainerIndex < 0 || overContainerIndex < 0) {
      releaseClickSuppression();
      return;
    }

    const nextContainers = deepCloneContainers(containers);

    if (activeContainerIndex === overContainerIndex && !overIsContainer) {
      const activeIndex = nextContainers[activeContainerIndex].items.findIndex((item) => item.id === active.id);
      const overIndex = nextContainers[overContainerIndex].items.findIndex((item) => item.id === over.id);
      if (activeIndex >= 0 && overIndex >= 0 && activeIndex !== overIndex) {
        nextContainers[activeContainerIndex].items = arrayMove(
          nextContainers[activeContainerIndex].items,
          activeIndex,
          overIndex
        );
      }
    }

    setContainers(nextContainers);
    pushValue(buildPayload("reorder", nextContainers, active.id));
    releaseClickSuppression();
  };

  return (
    <div className="board-root" ref={rootRef}>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <div className="board-grid">
          {containers.map((container) => (
            <Lane
              key={container.id}
              container={container}
              suppressClickRef={suppressClickRef}
              onCardClick={handleCardClick}
              onClaimClick={handleClaimClick}
            />
          ))}
        </div>
        <DragOverlay>
          {activeItem ? (
            <div className="failure-card dragging overlay">
              <div className="failure-card-top">
                <div className="failure-card-title">{activeItem.title}</div>
                <div className="failure-card-actions">
                <div className={`assignee-badge ${activeItem.assignee ? "filled" : ""}`}>
                  {activeItem.assigneeInitials || "+"}
                </div>
                <div className="drag-handle">::</div>
                </div>
              </div>
              <div className="failure-card-content static">
                <div className="failure-card-summary">{activeItem.summary}</div>
                <div className="failure-card-meta">{activeItem.meta}</div>
              </div>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

export default withStreamlitConnection(FailureBoardComponent);
