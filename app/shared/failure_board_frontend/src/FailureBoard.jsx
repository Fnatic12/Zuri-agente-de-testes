import React, { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib";

function deepCloneContainers(items) {
  return (items || []).map((container) => ({
    ...container,
    items: [...(container.items || [])],
  }));
}

function findContainerId(containers, itemId) {
  for (const container of containers || []) {
    if ((container.items || []).some((item) => item.id === itemId)) {
      return container.id;
    }
  }
  return null;
}

function getItemById(containers, itemId) {
  for (const container of containers || []) {
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

function sameDropTarget(left, right) {
  if (!left && !right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return left.laneId === right.laneId && left.index === right.index;
}

function clampIndex(index, max) {
  const numericIndex = Number.isFinite(index) ? Number(index) : max;
  return Math.max(0, Math.min(max, numericIndex));
}

function moveCard(containers, itemId, targetLaneId, targetIndex) {
  if (!itemId || !targetLaneId) {
    return containers;
  }

  const sourceLaneId = findContainerId(containers, itemId);
  if (!sourceLaneId) {
    return containers;
  }

  const sourceLane = containers.find((container) => container.id === sourceLaneId);
  const targetLane = containers.find((container) => container.id === targetLaneId);
  if (!sourceLane || !targetLane) {
    return containers;
  }

  const sourceItems = sourceLane.items || [];
  const targetItems = targetLane.items || [];
  const sourceIndex = sourceItems.findIndex((item) => item.id === itemId);
  if (sourceIndex < 0) {
    return containers;
  }

  let insertIndex = clampIndex(targetIndex, targetItems.length);
  if (sourceLaneId === targetLaneId && sourceIndex < insertIndex) {
    insertIndex -= 1;
  }

  if (sourceLaneId === targetLaneId && sourceIndex === insertIndex) {
    return containers;
  }

  const nextContainers = deepCloneContainers(containers);
  const nextSourceLane = nextContainers.find((container) => container.id === sourceLaneId);
  const nextTargetLane = nextContainers.find((container) => container.id === targetLaneId);
  if (!nextSourceLane || !nextTargetLane) {
    return containers;
  }

  const nextSourceItems = nextSourceLane.items || [];
  const nextSourceIndex = nextSourceItems.findIndex((item) => item.id === itemId);
  if (nextSourceIndex < 0) {
    return containers;
  }

  const [movedItem] = nextSourceItems.splice(nextSourceIndex, 1);
  if (!movedItem) {
    return containers;
  }

  const nextTargetItems = nextTargetLane.items || [];
  const boundedIndex = clampIndex(insertIndex, nextTargetItems.length);
  nextTargetItems.splice(boundedIndex, 0, movedItem);
  return nextContainers;
}

function DropIndicator() {
  return <div className="drop-indicator" aria-hidden="true" />;
}

function BoardCard({
  item,
  laneId,
  index,
  isDragSource,
  suppressClickRef,
  onCardClick,
  onClaimClick,
  onCardDragStart,
  onCardDragEnd,
  onCardDragOver,
}) {
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

  const stopCardDrag = (event) => {
    event.stopPropagation();
  };

  const handleDragStart = (event) => {
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(item.id));
    }
    onCardDragStart(item.id, laneId, index);
  };

  const handleDragEnd = () => {
    onCardDragEnd();
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const shouldInsertAfter = event.clientY > rect.top + rect.height / 2;
    onCardDragOver(laneId, shouldInsertAfter ? index + 1 : index);
  };

  return (
    <div
      className={`failure-card ${isDragSource ? "drag-source" : ""}`}
      draggable
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragOver={handleDragOver}
      role="button"
      tabIndex={0}
    >
      <div className="failure-card-top">
        <div className="failure-card-title">{item.title}</div>
        <div className="failure-card-actions">
          <button
            className={`assignee-badge ${item.assignee ? "filled" : ""}`}
            draggable={false}
            onClick={handleClaimClick}
            onMouseDown={stopCardDrag}
            onPointerDown={stopCardDrag}
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

function Lane({
  container,
  activeDrag,
  dropTarget,
  suppressClickRef,
  onCardClick,
  onClaimClick,
  onCardDragStart,
  onCardDragEnd,
  onLaneDragOver,
  onLaneDrop,
}) {
  const items = container.items || [];
  const isActiveTarget = activeDrag && dropTarget?.laneId === container.id;

  const handleLaneDragOver = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
    onLaneDragOver(container.id, items.length);
  };

  const handleLaneDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    onLaneDrop(container.id);
  };

  return (
    <div className={`lane-shell lane-${String(container.id || "").toLowerCase()}`}>
      <div className={`lane-header lane-header-${String(container.id || "").toLowerCase()}`}>{container.header}</div>
      <div className={`lane-body ${isActiveTarget ? "drag-target" : ""}`} onDragOver={handleLaneDragOver} onDrop={handleLaneDrop}>
        {items.map((item, index) => (
          <Fragment key={item.id}>
            {dropTarget?.laneId === container.id && dropTarget.index === index ? <DropIndicator /> : null}
            <BoardCard
              item={item}
              laneId={container.id}
              index={index}
              isDragSource={activeDrag?.itemId === item.id}
              suppressClickRef={suppressClickRef}
              onCardClick={onCardClick}
              onClaimClick={onClaimClick}
              onCardDragStart={onCardDragStart}
              onCardDragEnd={onCardDragEnd}
              onCardDragOver={onLaneDragOver}
            />
          </Fragment>
        ))}
        {dropTarget?.laneId === container.id && dropTarget.index === items.length ? <DropIndicator /> : null}
      </div>
    </div>
  );
}

function FailureBoardComponent(props) {
  const args = props?.args ?? {};
  const itemsArg = args.items ?? [];
  const itemsSignature = useMemo(() => JSON.stringify(itemsArg || []), [itemsArg]);
  const initialItems = useMemo(() => deepCloneContainers(itemsArg), [itemsSignature]);
  const [containers, setContainers] = useState(initialItems);
  const [activeDrag, setActiveDrag] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const rootRef = useRef(null);
  const gridRef = useRef(null);
  const suppressClickRef = useRef(false);
  const committedContainersRef = useRef(initialItems);
  const dropHandledRef = useRef(false);
  const frameHeightRef = useRef(0);

  const syncFrameHeight = () => {
    window.requestAnimationFrame(() => {
      const rootNode = rootRef.current;
      const gridNode = gridRef.current || rootNode?.firstElementChild;
      if (!rootNode || !gridNode) {
        return;
      }

      const rootStyles = window.getComputedStyle(rootNode);
      const paddingTop = parseFloat(rootStyles.paddingTop || "0") || 0;
      const paddingBottom = parseFloat(rootStyles.paddingBottom || "0") || 0;
      const gridRectHeight = Math.ceil(gridNode.getBoundingClientRect?.().height ?? 0);
      const gridScrollHeight = Math.ceil(gridNode.scrollHeight ?? 0);
      const nextHeight = Math.max(gridRectHeight, gridScrollHeight, 0) + Math.ceil(paddingTop + paddingBottom);

      if (nextHeight > 0 && Math.abs(nextHeight - frameHeightRef.current) > 1) {
        frameHeightRef.current = nextHeight;
        Streamlit.setFrameHeight(nextHeight);
      }
    });
  };

  useEffect(() => {
    if (activeDrag) {
      return;
    }
    const nextContainers = deepCloneContainers(itemsArg);
    committedContainersRef.current = nextContainers;
    setContainers(nextContainers);
  }, [itemsSignature, itemsArg, activeDrag]);

  useEffect(() => {
    syncFrameHeight();
  }, [containers, activeDrag, dropTarget]);

  useEffect(() => {
    const gridNode = gridRef.current || rootRef.current?.firstElementChild;
    if (!gridNode || typeof ResizeObserver === "undefined") {
      syncFrameHeight();
      return undefined;
    }

    const observer = new ResizeObserver(() => {
      syncFrameHeight();
    });
    observer.observe(gridNode);

    return () => {
      observer.disconnect();
    };
  }, []);

  const pushValue = (payload) => {
    Streamlit.setComponentValue(payload);
    syncFrameHeight();
  };

  const releaseClickSuppression = () => {
    window.setTimeout(() => {
      suppressClickRef.current = false;
    }, 320);
  };

  const clearDragInteraction = () => {
    setActiveDrag(null);
    setDropTarget(null);
    releaseClickSuppression();
  };

  const handleCardClick = (itemId) => {
    pushValue(buildPayload("click", containers, itemId));
  };

  const handleClaimClick = (itemId) => {
    pushValue(buildPayload("claim", containers, itemId));
  };

  const handleCardDragStart = (itemId, laneId, index) => {
    suppressClickRef.current = true;
    dropHandledRef.current = false;
    setActiveDrag({ itemId, laneId, index });
    setDropTarget({ laneId, index });
  };

  const handleCardDragEnd = () => {
    if (dropHandledRef.current) {
      return;
    }
    setContainers(committedContainersRef.current);
    clearDragInteraction();
  };

  const handleLaneDragOver = (laneId, index) => {
    if (!activeDrag) {
      return;
    }
    const nextTarget = { laneId, index };
    if (!sameDropTarget(dropTarget, nextTarget)) {
      setDropTarget(nextTarget);
    }
  };

  const handleLaneDrop = (laneId) => {
    if (!activeDrag) {
      return;
    }

    dropHandledRef.current = true;
    const fallbackLane = containers.find((container) => container.id === laneId);
    const target = dropTarget?.laneId === laneId
      ? dropTarget
      : { laneId, index: (fallbackLane?.items || []).length };

    const nextContainers = moveCard(
      committedContainersRef.current,
      activeDrag.itemId,
      target.laneId,
      target.index
    );

    if (nextContainers !== committedContainersRef.current) {
      committedContainersRef.current = nextContainers;
      setContainers(nextContainers);
      pushValue(buildPayload("reorder", nextContainers, activeDrag.itemId));
    }

    clearDragInteraction();
    window.setTimeout(() => {
      dropHandledRef.current = false;
    }, 0);
  };

  return (
    <div className="board-root" ref={rootRef}>
      <div className="board-grid" ref={gridRef}>
        {containers.map((container) => (
          <Lane
            key={container.id}
            container={container}
            activeDrag={activeDrag}
            dropTarget={dropTarget}
            suppressClickRef={suppressClickRef}
            onCardClick={handleCardClick}
            onClaimClick={handleClaimClick}
            onCardDragStart={handleCardDragStart}
            onCardDragEnd={handleCardDragEnd}
            onLaneDragOver={handleLaneDragOver}
            onLaneDrop={handleLaneDrop}
          />
        ))}
      </div>
    </div>
  );
}

export default withStreamlitConnection(FailureBoardComponent);
